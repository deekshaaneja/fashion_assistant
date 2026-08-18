"""DesignGenerationProvider: the pluggable creative-candidate-generation
boundary (Phase 2, sections 20-22). Structured constraints in, structured
`DesignCandidate`s out -- the provider proposes; deterministic validation
downstream (`src/fashion_engine/design/validation.py`) disposes. A provider
must never be trusted to silently respect fabric/construction constraints --
every candidate it returns is re-checked against the same `DesignConstraints`
regardless of which provider produced it.

Phase 2 performance fix: a provider's own job is only to produce a
`GeneratedDesignContent` (creative fields only -- title, construction,
neckline, sleeves, bottom, dupatta, decoration level, design DNA, rationale,
risks). Everything deterministic (flare/lining forcing, decoration
treatments, finishing, fabric usage/consumption, the garment/silhouette
reference block) is assembled once by `assemble_candidate`, shared by every
provider -- see `src/fashion_engine/design/assembly.py`.

Multi-direction generation fix: for `count > 1`, each design direction is
its own INDEPENDENT chat-completion call (never a single request asking for
several candidates at once -- that's what made a bigger schema/prompt blow
the time budget), run concurrently under a bounded thread pool, each given
its own creative "divergence objective" so the candidates are asked to
diverge by construction language rather than merely by color/title. A
candidate that turns out too similar to one already accepted triggers a
single targeted regeneration of just that candidate, explicitly told which
already-accepted candidates it must differ from -- never a blanket re-ask.

Mirrors the Phase 1 `LanguageModelProvider` pattern (`src/providers/llm.py`):
one narrow abstract contract, a deterministic default that needs no network
call, and a live implementation gated by the same `llm_enabled` setting.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from src.domain.enums import FlareLevel
from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_generation import (
    CandidateGenerationMetadata,
    DesignConstraints,
    DesignGenerationRequest,
)
from src.domain.models.design_proposal import (
    BottomSpec,
    ConstructionCreative,
    DecorationCreative,
    DesignCandidate,
    DupattaCreative,
    GeneratedDesignContent,
    NecklineCreative,
)
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment, Silhouette
from src.fashion_engine.design.archetypes import (
    DesignArchetype,
    get_design_archetypes,
    score_archetype_fit,
    select_diverse,
)
from src.fashion_engine.design.assembly import assemble_candidate
from src.fashion_engine.design.decoration import recommend_decoration
from src.fashion_engine.design.diversity import too_similar
from src.fashion_engine.design.dna import derive_target_dna
from src.fashion_engine.design.dupatta import recommend_dupatta
from src.fashion_engine.design.neckline import recommend_neckline
from src.fashion_engine.design.sleeves import recommend_sleeves
from src.providers.settings import get_settings
from src.rules.repository import get_garment_repository, get_silhouette_repository

logger = logging.getLogger(__name__)

# --- Bounded provider timing (see docs/design-engine.md) -- every external
# call has a hard per-call ceiling, and the WHOLE provider.generate() call
# (all candidates, all attempts, all regenerations combined) has its own
# hard wall-clock budget it will never exceed. Retries only ever happen for
# a transport failure, invalid JSON, or schema-invalid output for THAT ONE
# candidate -- never because a design is "aesthetically weak" (the
# application pipeline's job, downstream of generation), and never by
# discarding already-successful sibling candidates.
_HTTP_CALL_TIMEOUT_S = 20  # single /chat/completions call ceiling
_PROVIDER_TOTAL_BUDGET_S = 45  # whole generate() call, all candidates/attempts combined
_MAX_TOTAL_ATTEMPTS = 2  # per candidate: 1 initial + at most 1 repair round -- never unbounded
_MIN_USEFUL_REMAINING_S = 2.0  # not enough time left to bother starting another call
_MAX_CONCURRENCY = 6  # bounded -- never spawn one thread per candidate with no ceiling

# Creative search directions offered to independent candidates for count>1 --
# NOT hardcoded garment templates; the garment/silhouette/fabric/constraints
# are identical across all of them, only the construction-language framing
# differs, and the model is still free to interpret it within the fixed
# design vocabulary/hard constraints.
_DIVERGENCE_OBJECTIVES: tuple[tuple[str, str], ...] = (
    (
        "fluid_romantic",
        "Lean FLUID and ROMANTIC -- soft curved lines, gentle draping, an organic/soft silhouette language.",
    ),
    (
        "contemporary_architectural",
        "Lean CONTEMPORARY and ARCHITECTURAL -- clean structured lines, geometric paneling, a sharp/modern "
        "silhouette language.",
    ),
    (
        "layered_fusion",
        "Lean LAYERED and FUSION -- unexpected layering or cross-silhouette blending, textural contrast.",
    ),
)


class DesignGenerationProvider(ABC):
    @abstractmethod
    def generate(self, request: DesignGenerationRequest) -> list[DesignCandidate]:
        """Returns up to `request.count` structured candidates. Never
        raises -- on unrecoverable failure, returns an empty list so the
        caller can fall back to another provider."""


_FLARE_LEVEL_ORDER = [FlareLevel.MINIMAL, FlareLevel.MODERATE, FlareLevel.HIGH, FlareLevel.DRAMATIC]


def _preferred_flare_level(archetype: DesignArchetype, ceiling: str) -> FlareLevel | None:
    """Phase 3.1, section 2-3: `archetype.preferred_flare_level` already
    existed but was previously only used for archetype *selection* fit
    scoring, never to actually set a candidate's flare level -- every
    template-generated design silently got the fabric's ceiling regardless
    of the archetype's own character (e.g. a minimal/draped archetype
    getting the same full flare as a heritage-traditional one). Picks the
    archetype's own highest preferred level that still respects the
    ceiling; None (defer to the ceiling as DEFAULT) if none of its
    preferences fit under it."""
    ceiling_idx = _FLARE_LEVEL_ORDER.index(FlareLevel(ceiling))
    valid_values = {member.value for member in FlareLevel}
    candidates = [FlareLevel(v) for v in archetype.preferred_flare_level if v in valid_values]
    fitting = [level for level in candidates if _FLARE_LEVEL_ORDER.index(level) <= ceiling_idx]
    return max(fitting, key=_FLARE_LEVEL_ORDER.index) if fitting else None


def _bottom_for(garment: Garment, flare_construction: str) -> BottomSpec | None:
    if "bottom" not in garment.typical_components:
        return None
    if flare_construction in ("gathered", "dramatic"):
        bottom_type = "churidar" if garment.wear_category == "indian" else "flared skirt"
    else:
        bottom_type = "straight trousers" if garment.wear_category == "indian" else "fitted skirt"
    rationale = f"Matches the {flare_construction} construction above."
    return BottomSpec(type=bottom_type, fabric_role="main", rationale=rationale)


class TemplateDesignGenerationProvider(DesignGenerationProvider):
    """Deterministic default -- no LLM, no network call. Selects
    structurally diverse archetypes (DNA distance + fit against the actual
    silhouette's own structure/flare_construction) and elaborates each into
    a `GeneratedDesignContent` via the same rule-based sub-tools a live
    provider's output is validated against, then hands off to the shared
    `assemble_candidate` for deterministic post-processing -- the same
    assembly step the live provider uses, so the two never diverge."""

    def generate(self, request: DesignGenerationRequest) -> list[DesignCandidate]:
        garment = get_garment_repository().get(request.garment_id)
        silhouette = get_silhouette_repository().get(request.silhouette_id)
        if garment is None or silhouette is None:
            return []

        target_dna = derive_target_dna(request.client_brief)
        archetypes = get_design_archetypes()
        scored = [
            (archetype, garment, silhouette, score_archetype_fit(archetype, target_dna, garment, silhouette))
            for archetype in archetypes
        ]
        selected = select_diverse(scored, count=request.count)

        return [
            self._instantiate(archetype, request.fabric, g, s, request, target_dna)
            for archetype, g, s, _ in selected
        ]

    def _instantiate(
        self,
        archetype: DesignArchetype,
        fabric: Fabric,
        garment: Garment,
        silhouette: Silhouette,
        request: DesignGenerationRequest,
        target_dna: DesignDNA,
    ) -> DesignCandidate:
        constraints = request.constraints
        blended_dna = DesignDNA(
            **{
                axis: round(getattr(archetype.design_dna, axis) * 0.7 + getattr(target_dna, axis) * 0.3, 2)
                for axis in archetype.design_dna.as_vector()
            }
        )

        neckline = recommend_neckline(
            fabric, silhouette, blended_dna, request.client_brief, candidate_families=archetype.neckline_families
        )
        sleeve_family = archetype.sleeve_families[0]
        sleeves = recommend_sleeves(
            fabric,
            request.client_brief,
            candidate_length=sleeve_family.length,
            candidate_style=sleeve_family.style,
        )
        dupatta = recommend_dupatta(garment, fabric, archetype.dupatta_philosophy, request.client_brief)
        decoration = recommend_decoration(fabric, archetype.decoration_philosophy, request.client_brief)
        bottom = _bottom_for(garment, constraints.flare_construction)

        flare_level = _preferred_flare_level(archetype, constraints.effective_flare_level)
        flare_level_desc = flare_level.value if flare_level else constraints.effective_flare_level
        construction = ConstructionCreative(
            bodice_style=archetype.bodice_style,
            panelling=archetype.panelling,
            waist_placement=archetype.waist_placement,
            garment_length=request.client_brief.preferred_length or archetype.garment_length,
            hem_treatment=archetype.hem_treatment,
            flare_level=flare_level,
            rationale=(
                f"{fabric.name}'s structural character ({fabric.properties.drape or 'unspecified drape'}, "
                f"{fabric.properties.structure or 'unspecified structure'}) fits {archetype.name.lower()}'s "
                f"{archetype.bodice_style} at a {flare_level_desc} flare."
            ),
        )
        neckline_creative = NecklineCreative(
            type=neckline.type, depth=neckline.depth, rationale=neckline.rationale
        )
        dupatta_creative = (
            DupattaCreative(
                included=dupatta.included,
                fabric_role=dupatta.fabric_role,
                fabric_description=dupatta.fabric_description,
                color_strategy=dupatta.color_strategy,
                weight=dupatta.weight,
                transparency=dupatta.transparency,
                border=dupatta.border,
                embellishment=dupatta.embellishment,
                ombre_direction=dupatta.ombre_direction,
                rationale=dupatta.rationale,
            )
            if dupatta is not None
            else None
        )
        decoration_creative = DecorationCreative(level=decoration.level, rationale=decoration.rationale)

        drape_desc = fabric.properties.drape or "its drape"
        transparency_desc = fabric.properties.transparency or "opacity unspecified"
        rationale = [
            f"{fabric.name} ({drape_desc}, {transparency_desc}) drives {archetype.name.lower()}'s construction "
            f"language on this {silhouette.name}.",
            *(
                [f"Occasion: {request.fashion_context.occasion.replace('_', ' ')}."]
                if request.fashion_context.occasion
                else []
            ),
            decoration_creative.rationale,
        ]
        if dupatta_creative is not None:
            rationale.append(dupatta_creative.rationale)

        content = GeneratedDesignContent(
            title=f"{archetype.name} {silhouette.name}",
            design_intent=archetype.description,
            construction=construction,
            neckline=neckline_creative,
            sleeves=sleeves,
            bottom=bottom,
            dupatta=dupatta_creative,
            decoration=decoration_creative,
            supporting_fabrics=[],
            design_dna=blended_dna,
            rationale=rationale,
            risks=[],
        )
        return assemble_candidate(content, fabric, garment, silhouette, constraints)


_RESPONSE_JSON_SCHEMA = GeneratedDesignContent.model_json_schema()


@dataclass
class _CandidateResult:
    """One independent candidate-generation attempt's outcome -- produced
    inside a worker thread (or, for a targeted diversity regeneration, the
    main thread) and never mutates provider instance state, so it's safe to
    build concurrently."""

    candidate: DesignCandidate | None
    objective_id: str
    objective_text: str | None
    attempts: int
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    error_code: str | None


def _sum_optional(*values: int | None) -> int | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _objectives_for(count: int) -> list[tuple[str, str | None]]:
    if count <= 1:
        return [("primary", None)]
    objectives: list[tuple[str, str | None]] = []
    n = len(_DIVERGENCE_OBJECTIVES)
    for i in range(count):
        obj_id, obj_text = _DIVERGENCE_OBJECTIVES[i % n]
        if i >= n:
            obj_id = f"{obj_id}_v{i // n + 1}"
        objectives.append((obj_id, obj_text))
    return objectives


class OpenAICompatibleDesignGenerationProvider(DesignGenerationProvider):
    """Talks to an OpenAI-compatible /chat/completions endpoint (Aliyun
    DashScope, Qwen3.7-plus) to CREATIVELY ELABORATE within the same design
    vocabulary/hard constraints the template provider uses -- it does not
    invent construction language from nothing, and it does not decide
    validity or compute anything deterministic (scores, consumption,
    treatments); that is `assemble_candidate` and
    `src/fashion_engine/design/validation.py`'s job, run unconditionally on
    whatever comes back.

    For `count > 1`, each design direction is generated by its own
    independent request (never one request asked for several candidates),
    run concurrently under a bounded thread pool, each given a distinct
    creative divergence objective. A candidate that lands too similar to an
    already-accepted one triggers exactly one targeted regeneration of that
    candidate, explicitly told what to differ from -- it never silently
    discards a successful sibling candidate to do so."""

    def __init__(self) -> None:
        # Populated by generate() -- read by the orchestrator afterward for
        # structured debug timing and a clear, specific failure reason
        # (never hides behind a generic "something went wrong"). Only ever
        # written from the main thread, after all worker threads have
        # finished, so there is no concurrent-write race.
        self.last_timing_ms: dict[str, float] = {}
        self.last_error: str | None = None
        self.last_error_code: str | None = None
        self.last_attempts: int = 0
        self.last_usage: dict[str, int | None] | None = None
        self.last_candidate_metadata: list[CandidateGenerationMetadata] = []

    def generate(self, request: DesignGenerationRequest) -> list[DesignCandidate]:
        settings = get_settings()
        garment = get_garment_repository().get(request.garment_id)
        silhouette = get_silhouette_repository().get(request.silhouette_id)
        self.last_candidate_metadata = []
        if garment is None or silhouette is None:
            self.last_error = f"unknown garment/silhouette ({request.garment_id}/{request.silhouette_id})"
            self.last_error_code = "MODEL_PROVIDER_ERROR"
            return []

        deadline = time.monotonic() + _PROVIDER_TOTAL_BUDGET_S
        objectives = _objectives_for(request.count)

        t0 = time.monotonic()
        results = self._run_concurrent(objectives, request, settings, garment, silhouette, deadline)

        final: list[DesignCandidate] = []
        metadata: list[CandidateGenerationMetadata] = []
        for result in results:
            candidate = result.candidate
            retry: _CandidateResult | None = None

            if candidate is not None and any(too_similar(candidate, kept) for kept in final):
                remaining = deadline - time.monotonic()
                if remaining > _MIN_USEFUL_REMAINING_S:
                    retry = self._generate_one(
                        garment,
                        silhouette,
                        request,
                        settings,
                        deadline,
                        result.objective_id,
                        result.objective_text,
                        list(final),
                    )
                    candidate = retry.candidate
                    if candidate is not None and any(too_similar(candidate, kept) for kept in final):
                        candidate = None  # still a cosmetic variation even after being told what to avoid
                else:
                    candidate = None  # no budget left to regenerate -- drop rather than pad with a duplicate

            if candidate is not None:
                final.append(candidate)
            metadata.append(
                self._candidate_metadata(result, retry, accepted=candidate is not None, model=settings.llm_model)
            )

        call_ms = (time.monotonic() - t0) * 1000
        self.last_candidate_metadata = metadata
        self.last_attempts = max((m.attempts for m in metadata), default=0)
        self.last_usage = {
            "prompt_tokens": _sum_optional(*(m.input_tokens for m in metadata)),
            "completion_tokens": _sum_optional(*(m.output_tokens for m in metadata)),
            "reasoning_tokens": None,
        }
        self.last_timing_ms = {"parse_ms": 0.0, "call_ms": round(call_ms, 1)}

        self.last_error = None
        self.last_error_code = None
        if not final:
            failures = [m.error for m in metadata if m.error]
            self.last_error = "; ".join(failures) if failures else "provider returned no usable candidates"
            self.last_error_code = "MODEL_PROVIDER_ERROR"
        elif len(final) < request.count:
            self.last_error = f"only {len(final)} of {request.count} candidate(s) generated successfully"
            self.last_error_code = "MODEL_PARTIAL_FAILURE"

        return final

    def _candidate_metadata(
        self,
        result: _CandidateResult,
        retry: _CandidateResult | None,
        accepted: bool,
        model: str,
    ) -> CandidateGenerationMetadata:
        attempts = result.attempts + (retry.attempts if retry else 0)
        latency_ms = round(result.latency_ms + (retry.latency_ms if retry else 0.0), 1)
        input_tokens = _sum_optional(result.input_tokens, retry.input_tokens if retry else None)
        output_tokens = _sum_optional(result.output_tokens, retry.output_tokens if retry else None)

        error = None
        error_code = None
        if not accepted:
            if retry is not None:
                error = retry.error or "still structurally too similar to an already-accepted candidate"
                error_code = retry.error_code or "DIVERSITY_REJECTED"
            elif result.candidate is None:
                error, error_code = result.error, result.error_code
            else:
                error = "structurally too similar to an already-accepted candidate; no time left to regenerate"
                error_code = "DIVERSITY_REJECTED"

        return CandidateGenerationMetadata(
            provider="openai_compatible",
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            attempts=attempts,
            divergence_objective=result.objective_id,
            succeeded=accepted,
            error=error,
            error_code=error_code,
        )

    def _run_concurrent(
        self,
        objectives: list[tuple[str, str | None]],
        request: DesignGenerationRequest,
        settings,
        garment: Garment,
        silhouette: Silhouette,
        deadline: float,
    ) -> list[_CandidateResult]:
        results: list[_CandidateResult | None] = [None] * len(objectives)
        max_workers = max(1, min(_MAX_CONCURRENCY, len(objectives)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    self._generate_one, garment, silhouette, request, settings, deadline, obj_id, obj_text, []
                ): i
                for i, (obj_id, obj_text) in enumerate(objectives)
            }
            for future in concurrent.futures.as_completed(futures):
                results[futures[future]] = future.result()
        return results

    def _generate_one(
        self,
        garment: Garment,
        silhouette: Silhouette,
        request: DesignGenerationRequest,
        settings,
        deadline: float,
        objective_id: str,
        objective_text: str | None,
        differ_from: list[DesignCandidate],
    ) -> _CandidateResult:
        """Generates exactly ONE `GeneratedDesignContent` via its own
        independent chat-completion call(s), bounded to `_MAX_TOTAL_ATTEMPTS`
        against the SHARED provider deadline (never its own separate
        budget) -- runs inside a worker thread when count > 1, or on the
        main thread for a targeted diversity regeneration. Never raises."""
        prompt = _build_single_prompt(request, garment, silhouette, objective_text, differ_from)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        attempts = 0
        latency_ms = 0.0
        input_tokens: int | None = None
        output_tokens: int | None = None
        error: str | None = None
        error_code: str | None = None

        try:
            for attempt in range(1, _MAX_TOTAL_ATTEMPTS + 1):
                attempts = attempt
                remaining = deadline - time.monotonic()
                if remaining <= _MIN_USEFUL_REMAINING_S:
                    error = f"time budget exhausted before candidate '{objective_id}' could be generated"
                    error_code = "MODEL_PROVIDER_TIMEOUT"
                    break

                call_timeout = min(_HTTP_CALL_TIMEOUT_S, remaining)
                t0 = time.monotonic()
                content, usage, call_error, call_error_code = self._call_once(
                    messages, settings, attempt, call_timeout
                )
                latency_ms += (time.monotonic() - t0) * 1000
                if usage is not None:
                    input_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens")
                if content is None:
                    error, error_code = call_error, call_error_code
                    continue

                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as exc:
                    logger.warning("Candidate '%s' response was not valid JSON: %s", objective_id, exc)
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {"role": "user", "content": f"That was not valid JSON ({exc}). Respond with ONLY JSON."}
                    )
                    error, error_code = f"invalid JSON (attempt {attempt}): {exc}", "MODEL_OUTPUT_INVALID"
                    continue

                wrapped = isinstance(parsed, dict) and isinstance(parsed.get("candidates"), list)
                if wrapped and parsed["candidates"]:
                    parsed = parsed["candidates"][0]  # tolerate an old-style {"candidates": [...]} envelope

                try:
                    generated = GeneratedDesignContent(**parsed)
                except ValidationError as exc:
                    logger.info("Candidate '%s' failed schema validation: %s", objective_id, exc)
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"That failed schema validation: {exc}. Respond again with ONLY corrected "
                            "JSON matching the schema.",
                        }
                    )
                    error, error_code = f"schema-invalid (attempt {attempt}): {exc}", "MODEL_OUTPUT_INVALID"
                    continue

                candidate = assemble_candidate(generated, request.fabric, garment, silhouette, request.constraints)
                return _CandidateResult(
                    candidate=candidate,
                    objective_id=objective_id,
                    objective_text=objective_text,
                    attempts=attempts,
                    latency_ms=round(latency_ms, 1),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    error=None,
                    error_code=None,
                )
        except Exception as exc:  # never let a worker thread raise -- degrade to a failed result instead
            logger.exception("Unexpected error generating candidate '%s'", objective_id)
            error, error_code = f"unexpected error: {exc}", "MODEL_PROVIDER_ERROR"

        return _CandidateResult(
            candidate=None,
            objective_id=objective_id,
            objective_text=objective_text,
            attempts=attempts,
            latency_ms=round(latency_ms, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error,
            error_code=error_code,
        )

    def _call_once(
        self, messages: list[dict], settings, attempt: int, timeout_s: float
    ) -> tuple[str | None, dict[str, int | None] | None, str | None, str | None]:
        """Makes one bounded chat-completion call. Returns
        `(content, usage, error, error_code)` -- `content` is None (with a
        repair note already appended to `messages`) on any network/response
        failure or timeout, never blocks past `timeout_s`. Returns errors
        rather than mutating `self` so it's safe to call concurrently from
        multiple worker threads against one provider instance."""
        try:
            response = httpx.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": 0.6,
                    "max_tokens": settings.design_generation_max_tokens,
                    "enable_thinking": settings.design_generation_thinking,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "generated_design_content",
                            "schema": _RESPONSE_JSON_SCHEMA,
                            "strict": True,
                        },
                    },
                },
                timeout=timeout_s,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
            reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            parsed_usage = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": reasoning_tokens,
            }
            return content, parsed_usage, None, None
        except httpx.TimeoutException as exc:
            error = f"provider did not respond within {timeout_s:.0f}s (attempt {attempt}): {exc}"
            logger.warning("Design generation: %s", error)
            timeout_note = "Your last response timed out. Respond again with ONLY the JSON described."
            messages.append({"role": "user", "content": timeout_note})
            return None, None, error, "MODEL_PROVIDER_TIMEOUT"
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            error = f"provider call failed (attempt {attempt}): {exc}"
            logger.warning("Design generation: %s", error)
            repair_note = f"Your last response failed ({exc}). Respond again with ONLY the JSON described."
            messages.append({"role": "user", "content": repair_note})
            return None, None, error, "MODEL_PROVIDER_ERROR"


_SYSTEM_PROMPT = (
    "You are a boutique fashion design assistant. You propose creative construction/styling choices "
    "for an Indian fashion boutique WITHIN a fixed design vocabulary and hard fabric/construction "
    "constraints supplied to you. You never invent a construction choice that violates a stated constraint "
    "(e.g. a flare level above the stated ceiling, or an embellishment intensity above the stated ceiling). "
    "Within those ceilings, your construction.flare_level/flare_construction, decoration.treatments, and "
    "dupatta weight/transparency/border/embellishment/ombre_direction are genuine creative choices -- leave "
    "any of them null only when you have no specific preference, never as a way to avoid deciding. A lower "
    "flare level than the ceiling, or a different flare_construction than this silhouette's own default, is "
    "fine as long as it stays internally consistent (e.g. a 'dramatic' construction needs at least a 'high' "
    "flare level). You never compute scores, consumption, or fabric routing -- those are handled separately "
    "downstream. Respond with ONLY a single JSON object matching the given schema, no prose outside the "
    "JSON, no markdown fences."
)


def _archetype_menu_lines(archetypes: tuple[DesignArchetype, ...]) -> list[str]:
    return [f"- {a.id} ({a.name}): {a.description.strip()}" for a in archetypes]


def _differ_from_lines(differ_from: list[DesignCandidate]) -> list[str]:
    if not differ_from:
        return []
    lines = [
        "This concept MUST be structurally distinct from these already-accepted concepts -- use a different "
        "bodice/construction language, and do not just reuse their neckline/sleeve/bottom/dupatta/decoration "
        "choices with a different color or title:",
    ]
    for c in differ_from:
        dupatta_desc = "with a dupatta" if (c.dupatta and c.dupatta.included) else "no dupatta"
        bottom_desc = c.bottom.type if c.bottom else "no separate bottom"
        lines.append(
            f"- {c.title}: {c.construction.bodice_style}; {c.neckline.type} neckline; "
            f"{c.sleeves.length}/{c.sleeves.style} sleeves; {dupatta_desc}; bottom={bottom_desc}; "
            f"{c.decoration.level.lower()} decoration."
        )
    return lines


def _build_single_prompt(
    request: DesignGenerationRequest,
    garment: Garment,
    silhouette: Silhouette,
    objective_text: str | None,
    differ_from: list[DesignCandidate],
) -> str:
    """A compact design brief -- fabric properties, garment/silhouette,
    occasion, client preferences, hard constraints, and the design
    vocabulary -- never a serialized copy of the full output schema or any
    information the model would just be echoing back (section 4)."""
    fabric = request.fabric
    constraints: DesignConstraints = request.constraints
    brief = request.client_brief

    lines = [
        "Generate exactly 1 distinct design concept for this fabric + brief, matching the given JSON schema "
        "exactly (a single JSON object, not a list, not wrapped in any other key).",
        "",
        f"FABRIC: {fabric.name} ({fabric.category})",
        f"properties: {fabric.properties.model_dump(exclude_none=True)}",
        "",
        f"GARMENT: {request.garment_name} (wear_category={garment.wear_category})",
        f"SILHOUETTE: {request.silhouette_name}",
        f"OCCASION: {request.fashion_context.occasion or 'unspecified'}",
        "",
        "HARD CONSTRAINTS (never violate these):",
        f"- flare LEVEL ceiling (you may choose this level or anything lower, never higher): "
        f"{constraints.effective_flare_level}",
        f"- this silhouette's own flare CONSTRUCTION (default -- propose a different one only with good reason, "
        f"and keep it internally consistent with your chosen flare level): {constraints.flare_construction}",
        f"- decoration ceiling (not a target): {constraints.max_embellishment_intensity}",
        f"- lining required: {constraints.requires_lining}",
    ]
    if constraints.hard_avoid:
        lines.append(f"- avoid: {'; '.join(constraints.hard_avoid)}")
    if constraints.notes:
        lines.append(f"- Phase 1 notes: {'; '.join(constraints.notes)}")

    client_prefs = brief.model_dump(exclude_none=True, exclude_defaults=True)
    lines += [
        "",
        f"CLIENT PREFERENCES: {client_prefs or 'none stated'}",
        "",
        "DESIGN VOCABULARY (draw from or blend these -- do not invent an unrelated construction language):",
        *_archetype_menu_lines(get_design_archetypes()),
    ]
    if objective_text:
        lines += ["", f"CREATIVE DIRECTION FOR THIS CONCEPT: {objective_text}"]
    differ_lines = _differ_from_lines(differ_from)
    if differ_lines:
        lines += [""] + differ_lines
    return "\n".join(lines)


class MockDesignGenerationProvider(DesignGenerationProvider):
    """Deterministic, immediate provider for testing the
    generate-design-directions endpoint independently of any external model
    (`DESIGN_GENERATION_PROVIDER=mock`). Delegates to
    `TemplateDesignGenerationProvider`'s own candidate-building logic --
    never a second, parallel generation implementation -- but is selected
    and reported as its own distinct, explicitly-labeled provider so tests
    and ops tooling can assert exactly which path ran regardless of this
    machine's `LLM_ENABLED`/`.env` state."""

    def generate(self, request: DesignGenerationRequest) -> list[DesignCandidate]:
        return TemplateDesignGenerationProvider().generate(request)


def get_design_generation_provider() -> DesignGenerationProvider:
    settings = get_settings()
    mode = (settings.design_generation_provider or "auto").strip().lower()

    if mode == "mock":
        return MockDesignGenerationProvider()
    if mode == "template":
        return TemplateDesignGenerationProvider()
    if mode in ("live", "openai_compatible", "alibaba", "aliyun", "dashscope"):
        return OpenAICompatibleDesignGenerationProvider()

    # "auto" (default): matches every other provider in the kernel --
    # llm_enabled alone decides template vs. live.
    if not settings.llm_enabled:
        return TemplateDesignGenerationProvider()
    return OpenAICompatibleDesignGenerationProvider()
