"""FabricVisionProvider: the pluggable image-understanding boundary for
Phase 3 (sections 21-23). Structured image bytes in, a single compact
`VisionModelOutput` out -- the provider answers ONLY "what does this fabric
appear to be and what visual/material properties are supported by the
images?" (section 23). It never decides a garment, never computes anything
deterministic, and normalization/evidence-building/fusion happens entirely
in `src/fashion_engine/fabric/vision_evidence.py`, not here.

Mirrors the Phase 1 `LanguageModelProvider` / Phase 2
`DesignGenerationProvider` pattern: one narrow abstract contract, a
deterministic default that needs no network call, and a live implementation
gated by `VISION_ENABLED`. Bounded timeout/retry, matching the Phase 2
performance-fix architecture (section 37) -- never an unbounded retry loop.

Raw image bytes live ONLY in this module's `ProviderImage` -- never in a
domain model (section 32)."""
from __future__ import annotations

import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from pydantic import ValidationError

from src.domain.models.fabric_vision import (
    ImageRole,
    VisionBorderOut,
    VisionColorOut,
    VisionModelOutput,
)
from src.providers.settings import get_settings

logger = logging.getLogger(__name__)

# Bounded provider timing, mirroring the Phase 2 fix -- a vision call
# carries more payload (image tokens) than a text call, so the per-call
# ceiling is a little more generous, but still finite and never retried
# without limit.
_VISION_CALL_TIMEOUT_S = 25
_VISION_TOTAL_BUDGET_S = 40
_MAX_TOTAL_ATTEMPTS = 2  # 1 initial + at most 1 repair round
_MIN_USEFUL_REMAINING_S = 2.0

_ALLOWED_TRANSPARENCY = ("opaque", "semi_sheer", "sheer")
_ALLOWED_SHEEN = ("matte", "subtle_sheen", "high_sheen", "metallic")
_ALLOWED_DRAPE = ("crisp", "structured", "fluid", "soft", "stiff", "fluid_to_structured")
_ALLOWED_STIFFNESS = ("soft", "medium", "stiff")
_ALLOWED_STRUCTURE = ("fluid", "semi_structured", "structured")
_ALLOWED_SURFACE_DENSITY = ("none", "sparse", "moderate", "dense")
_ALLOWED_WEIGHT_CLASS = ("light", "medium", "heavy")
_ALLOWED_EMBELLISHMENT_TOLERANCE = ("low", "medium", "high")
_ALLOWED_EMBELLISHMENT_TYPES = (
    "zari",
    "zardozi",
    "aari",
    "threadwork",
    "mirror_work",
    "sequins",
    "cutdana",
    "beads",
    "pearls",
    "gota_patti",
    "applique",
    "lace",
    "embroidery",
    "piping",
    "metallic_thread",
    "printed",
    "woven_jacquard",
)
_ALLOWED_MOTIF_TYPES = (
    "floral",
    "geometric",
    "paisley",
    "abstract",
    "botanical",
    "traditional",
    "stripe",
    "check",
    "none",
    "other",
)


@dataclass
class ProviderImage:
    """Raw image bytes at the provider boundary only -- never held in a
    domain model."""

    image_id: str
    data: bytes
    content_type: str = "image/jpeg"
    role: ImageRole = ImageRole.UNKNOWN


@dataclass
class VisionProviderResult:
    output: VisionModelOutput | None
    attempts: int = 0
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    error_code: str | None = None
    warnings: list[str] = field(default_factory=list)


class FabricVisionProvider(ABC):
    @abstractmethod
    def analyze(self, images: list[ProviderImage], fabric_name_hint: str | None = None) -> VisionProviderResult:
        """Returns one fused `VisionModelOutput` for the whole image set, or
        `output=None` with `error`/`error_code` set on failure. Never
        raises."""


def _mock_dominant_colors(images: list[ProviderImage]) -> list[VisionColorOut]:
    from src.fashion_engine.fabric.vision_preprocess import decode_image

    colors: list[VisionColorOut] = []
    for image in images[:1]:
        decoded = decode_image(image.data)
        if decoded is None:
            continue
        small = decoded.resize((1, 1))
        r, g, b = small.getpixel((0, 0))
        hex_estimate = f"#{r:02x}{g:02x}{b:02x}"
        colors.append(VisionColorOut(name="dominant swatch color", hex_estimate=hex_estimate, role="dominant"))
    return colors


class MockFabricVisionProvider(FabricVisionProvider):
    """Deterministic default -- no network call. Derives what it honestly
    CAN derive from raw pixels (dominant color) via the same preprocessing
    module the real pipeline uses, and explicitly marks everything else as
    low/unknown certainty -- it must never be mistaken for a real
    vision-model evaluation (section 38), so it says so in its own output."""

    def analyze(self, images: list[ProviderImage], fabric_name_hint: str | None = None) -> VisionProviderResult:
        from src.domain.models.fabric_vision import VisionPropertyOut

        colors = _mock_dominant_colors(images)
        output = VisionModelOutput(
            image_subject="fabric_swatch",
            subject_reason="Mock provider assumes uploaded images are fabric swatches.",
            dominant_colors=colors,
            transparency=VisionPropertyOut(
                value="opaque", certainty="low", reason="Mock provider cannot assess transparency."
            ),
            sheen=VisionPropertyOut(value="matte", certainty="low", reason="Mock provider cannot assess sheen."),
            drape=VisionPropertyOut(certainty="unknown", reason="Mock provider does not infer drape."),
            stiffness=VisionPropertyOut(certainty="unknown", reason="Mock provider does not infer stiffness."),
            structure=VisionPropertyOut(certainty="unknown", reason="Mock provider does not infer structure."),
            surface_density=VisionPropertyOut(
                value="none", certainty="low", reason="Mock provider cannot assess surface work."
            ),
            weight_class=VisionPropertyOut(certainty="unknown", reason="Mock provider does not infer weight."),
            embellishment_tolerance=VisionPropertyOut(certainty="unknown"),
            fabric_family=VisionPropertyOut(
                value=fabric_name_hint, certainty="low" if fabric_name_hint else "unknown",
                reason="Mock provider does not perform real textile-family inference.",
            ),
            motifs=[],
            border=VisionBorderOut(present=False),
            embellishment_types=[],
            wear_potential_indian=0.5,
            wear_potential_western=0.5,
            wear_potential_fusion=0.5,
            wear_potential_reason="Mock provider -- no real wear-potential inference.",
            design_potential_signals=[],
            warnings=["This is a MOCK analysis for testing -- not a real vision-model evaluation."],
            suggested_additional_photos=[],
        )
        return VisionProviderResult(output=output, attempts=1, latency_ms=0.0)


_SYSTEM_PROMPT = (
    "You are a textile analyst for an Indian fashion boutique. You are given one or more photographs of the "
    "SAME physical fabric swatch (or possibly a garment, or possibly something else entirely). Your job is "
    "ONLY to report what is visually supported by the photographs -- never invent a fibre composition, exact "
    "GSM, exact width, or a specific trade/marketing name you cannot actually see. For every property, rate "
    "your own certainty as one of high/medium/low/unknown -- use 'unknown' whenever the photographs genuinely "
    "do not support a judgement, rather than guessing. Respond with ONLY a single JSON object matching the "
    "schema described, no prose outside the JSON, no markdown fences."
)


def _schema_instructions() -> str:
    return "\n".join(
        [
            "Return a single JSON object with exactly these top-level keys:",
            'image_subject: one of "fabric_swatch"|"garment"|"non_fabric"|"uncertain", subject_reason: string.',
            'dominant_colors: list of {"name": str, "hex_estimate": str|null, "proportion": 0-1|null, "role": '
            '"dominant"|"secondary"|"accent"|"metallic"} (image-estimated color, not calibrated physical color).',
            "Each of the following is an object {value, certainty, source_images, reason, alternative}: "
            "value is a string from the allowed list below (or null if certainty is 'unknown'); certainty is "
            'one of "high"|"medium"|"low"|"unknown"; source_images lists which image (by the label given, e.g. '
            '"image_1") supports the judgement; reason is one short sentence; alternative is a plausible second '
            "value if genuinely ambiguous, else null.",
            f"- transparency: allowed values {_ALLOWED_TRANSPARENCY}",
            f"- sheen: allowed values {_ALLOWED_SHEEN}",
            f"- drape: allowed values {_ALLOWED_DRAPE}",
            f"- stiffness: allowed values {_ALLOWED_STIFFNESS}",
            f"- structure: allowed values {_ALLOWED_STRUCTURE}",
            f"- surface_density: allowed values {_ALLOWED_SURFACE_DENSITY}",
            f"- weight_class: allowed values {_ALLOWED_WEIGHT_CLASS}",
            f"- embellishment_tolerance: allowed values {_ALLOWED_EMBELLISHMENT_TOLERANCE}",
            "- fabric_family: value is free text (your best probable textile family, e.g. 'organza', 'georgette' "
            "-- not a brand/trade name), certainty as above.",
            'motifs: list of {"motif_type": one of ' + str(_ALLOWED_MOTIF_TYPES) + ', "placement": '
            '"all_over"|"placement"|"border_only"|"none"|null, "scale": str|null, "density": str|null, '
            '"directional": bool|null}.',
            'border: null, or {"present": bool, "relative_width": "narrow"|"moderate"|"wide"|null, '
            '"decorative_density": str|null, "style": str|null, "directional": bool|null, '
            '"preserve_as_design_element": bool|null}.',
            f"embellishment_types: subset of {_ALLOWED_EMBELLISHMENT_TYPES} actually visible.",
            "wear_potential_indian, wear_potential_western, wear_potential_fusion: floats 0-1 each (not "
            "mutually exclusive), wear_potential_reason: one sentence.",
            "design_potential_signals: list of short high-level tags, e.g. 'STRUCTURED_OCCASIONWEAR', "
            "'FLUID_ROMANTIC' -- signals only, not garment recommendations.",
            "warnings: list of short caveats about this specific set of photographs (e.g. lighting, angle).",
            "suggested_additional_photos: list of short suggestions for what additional photo would improve "
            "the analysis (e.g. 'a drape/hanging view', 'a closer shot of the border'), or empty if not needed.",
        ]
    )


def _build_messages(
    images: list[ProviderImage], fabric_name_hint: str | None, repair_note: str | None = None
) -> list[dict]:
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                (f"The boutique owner says this fabric may be: {fabric_name_hint!r} (unconfirmed, treat as a "
                 f"hint only, verify against what you actually see).\n\n" if fabric_name_hint else "")
                + f"You are given {len(images)} photograph(s) of the same fabric, labeled below in order.\n"
                + _schema_instructions()
            ),
        }
    ]
    for i, image in enumerate(images, start=1):
        content.append({"type": "text", "text": f"image_{i} (declared role: {image.role}):"})
        b64 = base64.b64encode(image.data).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{image.content_type};base64,{b64}"}})

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    if repair_note:
        messages.append({"role": "user", "content": repair_note})
    return messages


class OpenAICompatibleFabricVisionProvider(FabricVisionProvider):
    """Talks to an OpenAI-compatible /chat/completions endpoint with
    multimodal `image_url` content parts (Aliyun DashScope, `qwen3-vl-plus`
    by default -- NOT the text-only `qwen3.7-plus` used for design
    generation, confirmed empirically that it does not accept images).

    Uses `response_format: json_object` + Pydantic validation + one bounded
    repair round rather than `json_schema` strict mode -- empirically,
    strict JSON-schema enforcement is NOT supported for this vision model
    on this endpoint (confirmed: the identical schema that works for the
    text model fails with an `invalid_parameter_error` here), which is
    exactly the documented fallback for that case (Phase 2, section 5)."""

    def analyze(self, images: list[ProviderImage], fabric_name_hint: str | None = None) -> VisionProviderResult:
        settings = get_settings()
        api_key = settings.vision_api_key or settings.llm_api_key
        messages = _build_messages(images, fabric_name_hint)

        deadline = time.monotonic() + _VISION_TOTAL_BUDGET_S
        attempt = 0
        latency_ms = 0.0
        input_tokens: int | None = None
        output_tokens: int | None = None
        error: str | None = None
        error_code: str | None = None

        for attempt in range(1, _MAX_TOTAL_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= _MIN_USEFUL_REMAINING_S:
                error = f"vision provider time budget exhausted after {attempt - 1} attempt(s)"
                error_code = "VISION_PROVIDER_TIMEOUT"
                break

            call_timeout = min(_VISION_CALL_TIMEOUT_S, remaining)
            t0 = time.monotonic()
            content, usage, call_error, call_error_code = self._call_once(
                messages, settings, api_key, attempt, call_timeout
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
                logger.warning("Vision response was not valid JSON: %s", exc)
                messages.append({"role": "assistant", "content": content})
                invalid_json_note = f"That was not valid JSON ({exc}). Respond with ONLY JSON."
                messages.append({"role": "user", "content": invalid_json_note})
                error, error_code = f"invalid JSON (attempt {attempt}): {exc}", "VISION_OUTPUT_INVALID"
                continue

            try:
                output = VisionModelOutput(**parsed)
            except ValidationError as exc:
                logger.info("Vision output failed schema validation: %s", exc)
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": f"That failed schema validation: {exc}. Respond again with ONLY corrected "
                        "JSON matching the schema.",
                    }
                )
                error, error_code = f"schema-invalid (attempt {attempt}): {exc}", "VISION_OUTPUT_INVALID"
                continue

            return VisionProviderResult(
                output=output,
                attempts=attempt,
                latency_ms=round(latency_ms, 1),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return VisionProviderResult(
            output=None,
            attempts=attempt,
            latency_ms=round(latency_ms, 1),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error or "vision provider returned no usable analysis",
            error_code=error_code or "VISION_PROVIDER_ERROR",
        )

    def _call_once(
        self, messages: list[dict], settings, api_key: str, attempt: int, timeout_s: float
    ) -> tuple[str | None, dict[str, int | None] | None, str | None, str | None]:
        try:
            response = httpx.post(
                f"{settings.vision_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                json={
                    "model": settings.vision_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": settings.vision_max_tokens,
                    "enable_thinking": False,
                    "response_format": {"type": "json_object"},
                },
                timeout=timeout_s,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
            parsed_usage = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            }
            return content, parsed_usage, None, None
        except httpx.TimeoutException as exc:
            error = f"vision provider did not respond within {timeout_s:.0f}s (attempt {attempt}): {exc}"
            logger.warning("Fabric vision: %s", error)
            timeout_note = "Your last response timed out. Respond again with ONLY the JSON described."
            messages.append({"role": "user", "content": timeout_note})
            return None, None, error, "VISION_PROVIDER_TIMEOUT"
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            error = f"vision provider call failed (attempt {attempt}): {exc}"
            logger.warning("Fabric vision: %s", error)
            repair_note = f"Your last response failed ({exc}). Respond again with ONLY the JSON described."
            messages.append({"role": "user", "content": repair_note})
            return None, None, error, "VISION_PROVIDER_ERROR"


def get_fabric_vision_provider() -> FabricVisionProvider:
    settings = get_settings()
    mode = (settings.vision_provider or "auto").strip().lower()

    if mode == "mock":
        return MockFabricVisionProvider()
    if mode in ("live", "openai_compatible", "alibaba", "aliyun", "dashscope"):
        return OpenAICompatibleFabricVisionProvider()

    if not settings.vision_enabled:
        return MockFabricVisionProvider()
    return OpenAICompatibleFabricVisionProvider()
