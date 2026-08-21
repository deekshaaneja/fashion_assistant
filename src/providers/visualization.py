"""DesignVisualizationProvider: the pluggable image-GENERATION boundary for
Phase 4 (sections 3, 8-10). A `VisualizationSpecification` + selected fabric
reference image(s) in, generated image bytes out -- the provider answers
ONLY "render this specification, conditioned on these fabric photographs."
It never decides design content (that's `DesignProposal`/
`VisualizationSpecification`, built upstream) and never validates its own
output (that's `visual_validate.py`, downstream).

Also hosts `GeneratedImageValidator` (section 16): a SEPARATE, narrow
vision-understanding call used only to ask "what is visibly present in this
generated image" -- reuses the Phase 3 vision-model credential/config by
default rather than a new one, and is intentionally not the same class as
the generation provider above (generation and validation are different
capabilities, potentially different models, and must stay swappable
independently).

Mirrors the Phase 2/3 provider pattern: one narrow abstract contract, a
deterministic default that needs no network call, and a live implementation
gated by `VISUALIZATION_ENABLED`. Bounded timeout/retry throughout -- never
an unbounded retry loop, never a hang on provider failure.

Provider-specific request/response shapes live ONLY in this module -- they
never leak into `src/domain/models/visualization.py` or
`src/fashion_engine/visualization/*` (section 3).
"""
from __future__ import annotations

import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from typing import Protocol

import httpx
from pydantic import ValidationError

from src.domain.models.visualization import GeneratedImageObservation, VisualizationSpecification
from src.providers.settings import get_settings

logger = logging.getLogger(__name__)

# --- Bounded provider timing (matches the Phase 2/3 fix -- see
# docs/design-engine.md / docs/vision-engine.md). Image generation is
# empirically slower than either text or vision-understanding calls
# (section 33: "the priority is a reliable bounded response, not an
# unrealistic low latency target"), so the ceilings here are more generous,
# but still finite.
_GENERATION_CALL_TIMEOUT_S = 90
_GENERATION_TOTAL_BUDGET_S = 150
_MAX_TOTAL_ATTEMPTS = 2  # 1 initial + at most 1 repair round, never unbounded
_MIN_USEFUL_REMAINING_S = 5.0

_VALIDATION_CALL_TIMEOUT_S = 25
_VALIDATION_TOTAL_BUDGET_S = 40
_MAX_VALIDATION_ATTEMPTS = 2


# --- Generation provider ---------------------------------------------------


@dataclass
class ReferenceImage:
    """Raw fabric-photo bytes at the provider boundary only -- never held in
    a domain model (matches Phase 3's `ProviderImage` convention)."""

    image_id: str
    data: bytes
    content_type: str = "image/jpeg"


@dataclass
class GeneratedImage:
    """Raw generated-image bytes at the provider boundary only -- the asset
    store (`fashion_engine/visualization/asset_store.py`) is what turns this
    into a stable, storable application reference."""

    data: bytes
    content_type: str = "image/png"


@dataclass
class VisualizationProviderRequest:
    specification: VisualizationSpecification
    reference_images: list[ReferenceImage]
    prompt: str
    count: int = 1


@dataclass
class VisualizationProviderResult:
    images: list[GeneratedImage] = field(default_factory=list)
    attempts: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    error_code: str | None = None


class DesignVisualizationProvider(ABC):
    @abstractmethod
    def generate(self, request: VisualizationProviderRequest) -> VisualizationProviderResult:
        """Returns generated image(s) for the specification, or
        `images=[]` with `error`/`error_code` set on failure. Never raises."""


class ImageEditCapableProvider(Protocol):
    """Phase 4.1, section 15-16: a capability, not a base class -- every
    staged operation (material prep, base composition, targeted design
    edit) composes on top of this ONE primitive. A provider satisfies this
    structurally (duck typing); it does not need to inherit anything."""

    def edit_image(self, image: ReferenceImage, prompt: str) -> VisualizationProviderResult:
        """An existing image + a text instruction -> a new image. Never
        raises; failures come back as `error`/`error_code`."""


def _placeholder_png(spec: VisualizationSpecification) -> bytes:
    """A tiny, deterministic, procedurally generated stand-in image -- good
    enough to exercise the storage/validation pipeline in tests; NEVER a
    substitute for a real generated visualization (mirrors Phase 3's
    `MockFabricVisionProvider` honesty convention -- section 31)."""
    from PIL import Image, ImageDraw

    color = (120, 20, 60)
    if spec.palette and spec.palette.colors:
        hex_color = next(iter(spec.palette.colors.values()), None)
        if hex_color and hex_color.startswith("#") and len(hex_color) == 7:
            color = tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))

    image = Image.new("RGB", (512, 768), color=color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 472, 728), outline=(255, 255, 255), width=3)
    label = f"MOCK: {spec.garment.category_name} / {spec.garment.silhouette_name}"
    draw.text((50, 50), label, fill=(255, 255, 255))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _placeholder_edit_png(prompt: str) -> bytes:
    """Mock stand-in for the staged pipeline's `edit_image` primitive --
    same honesty convention as `_placeholder_png` (never real fidelity)."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (512, 768), color=(90, 90, 90))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 472, 728), outline=(255, 255, 255), width=3)
    draw.text((50, 50), f"MOCK EDIT: {prompt[:60]}", fill=(255, 255, 255))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class MockDesignVisualizationProvider(DesignVisualizationProvider):
    """Deterministic default -- no network call, no real fabric/design
    fidelity (section 31: must never stand in as Phase 4 acceptance
    evidence). Exists purely so the storage/validation/API pipeline can be
    exercised without a live provider."""

    def generate(self, request: VisualizationProviderRequest) -> VisualizationProviderResult:
        images = [GeneratedImage(data=_placeholder_png(request.specification)) for _ in range(request.count)]
        return VisualizationProviderResult(images=images, attempts=1, latency_ms=0.0)

    def edit_image(self, image: ReferenceImage, prompt: str) -> VisualizationProviderResult:
        """Phase 4.1's staged-pipeline primitive, mocked -- ignores the
        input image (a real edit would condition on it) and returns a
        clearly-labeled placeholder, matching the same honesty convention
        as `generate()`."""
        return VisualizationProviderResult(images=[GeneratedImage(data=_placeholder_edit_png(prompt))], attempts=1)


def _extract_generated_images(message: dict) -> list[GeneratedImage]:
    """Handles the several response shapes an OpenAI-compatible image/edit
    model might use -- this gateway's actual behavior at investigation time
    (section 9) was an empty `message` with no image payload in any shape,
    for every image-capable model tried (`qwen-image`, `qwen-image-edit`,
    `qwen-image-edit-plus`, `wan2.7-image`); this function is written to the
    documented/plausible contract so it is correct the moment the account's
    image generation actually returns data, rather than assuming one exact
    shape works untested."""
    images: list[GeneratedImage] = []

    # Shape 1: `message.images` -- a DashScope multimodal-chat extension.
    for item in message.get("images") or []:
        url = (item.get("image_url") or {}).get("url") if isinstance(item, dict) else None
        if url and url.startswith("data:"):
            images.append(_decode_data_url(url))

    # Shape 2: `message.content` as a list of OpenAI-style content parts.
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    images.append(_decode_data_url(url))

    # Shape 3: `message.content` as a plain string containing a data URL.
    if isinstance(content, str) and "data:image" in content:
        start = content.find("data:image")
        end = content.find(")", start)
        url = content[start : end if end != -1 else None].strip()
        images.append(_decode_data_url(url))

    return images


def _decode_data_url(url: str) -> GeneratedImage:
    header, _, b64_data = url.partition(",")
    content_type = "image/png"
    if header.startswith("data:") and ";" in header:
        content_type = header[5:].split(";")[0] or content_type
    return GeneratedImage(data=base64.b64decode(b64_data), content_type=content_type)


class OpenAICompatibleDesignVisualizationProvider(DesignVisualizationProvider):
    """Talks to an OpenAI-compatible /chat/completions endpoint with
    multimodal `image_url` reference content parts (Aliyun DashScope,
    `qwen-image-edit` by default). Empirically confirmed via direct API
    investigation (section 9, documented in the Phase 4 report):

    - `/images/generations` and `/images/edits` are NOT routed on this
      account's gateway (404) -- the only working transport is
      `/chat/completions`, mirroring the vision-understanding provider.
    - `qwen-image-edit` requires 1-3 reference images per call ("input
      image count must be between 1 and 3") -- reference-conditioned
      generation IS supported in principle (section 10), which is why this
      is the default model rather than a pure text-to-image one.
    - Plain `qwen-image` text-to-image explicitly rejected as "Unsupported
      model for OpenAI compatibility mode."
    - Every image-capable model actually tried against this account
      returned HTTP 200 with an empty `message` (no image payload in any
      known shape) regardless of streaming/modalities/size parameters --
      this account's image generation does not currently return usable
      output despite validating the request shape. Treated as a structured
      `VISUALIZATION_OUTPUT_EMPTY` error, never silently accepted as
      success.
    """

    def _build_messages(
        self, prompt: str, references: list[ReferenceImage], repair_note: str | None = None
    ) -> list[dict]:
        """A SINGLE user message only -- empirically confirmed (section 9):
        this account's `qwen-image-edit` rejects any request with more than
        one message ("messages length only support 1"), so a retry must
        resend a fresh single-turn request, never append conversation
        history the way the text/vision providers do."""
        text = f"{prompt}\n\n{repair_note}" if repair_note else prompt
        content: list[dict] = [{"type": "text", "text": text}]
        for ref in references:
            b64 = base64.b64encode(ref.data).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:{ref.content_type};base64,{b64}"}})
        return [{"role": "user", "content": content}]

    def generate(self, request: VisualizationProviderRequest) -> VisualizationProviderResult:
        settings = get_settings()
        api_key = settings.visualization_api_key or settings.llm_api_key
        max_refs = settings.visualization_max_reference_images
        references = request.reference_images[:max_refs]

        deadline = time.monotonic() + _GENERATION_TOTAL_BUDGET_S
        latency_ms = 0.0
        error: str | None = None
        error_code: str | None = None
        attempt = 0
        repair_note: str | None = None

        for attempt in range(1, _MAX_TOTAL_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= _MIN_USEFUL_REMAINING_S:
                error = f"visualization provider time budget exhausted after {attempt - 1} attempt(s)"
                error_code = "VISUALIZATION_PROVIDER_TIMEOUT"
                break

            messages = self._build_messages(request.prompt, references, repair_note)
            call_timeout = min(_GENERATION_CALL_TIMEOUT_S, remaining)
            t0 = time.monotonic()
            message, call_error, call_error_code = self._call_once(
                messages, settings, api_key, attempt, call_timeout
            )
            latency_ms += (time.monotonic() - t0) * 1000
            if message is None:
                error, error_code = call_error, call_error_code
                continue

            images = _extract_generated_images(message)
            if not images:
                error = f"provider returned no image payload (attempt {attempt})"
                error_code = "VISUALIZATION_OUTPUT_EMPTY"
                repair_note = "Your last response did not include an image. Please generate one."
                continue

            return VisualizationProviderResult(images=images, attempts=attempt, latency_ms=round(latency_ms, 1))

        return VisualizationProviderResult(
            images=[],
            attempts=attempt,
            latency_ms=round(latency_ms, 1),
            error=error or "visualization provider returned no usable image",
            error_code=error_code or "VISUALIZATION_PROVIDER_ERROR",
        )

    def _call_once(
        self, messages: list[dict], settings, api_key: str, attempt: int, timeout_s: float
    ) -> tuple[dict | None, str | None, str | None]:
        try:
            response = httpx.post(
                f"{settings.visualization_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                json={
                    "model": settings.visualization_model,
                    "messages": messages,
                    "modalities": ["text", "image"],
                },
                timeout=timeout_s,
            )
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"], None, None
        except httpx.TimeoutException as exc:
            error = f"visualization provider did not respond within {timeout_s:.0f}s (attempt {attempt}): {exc}"
            logger.warning("Design visualization: %s", error)
            return None, error, "VISUALIZATION_PROVIDER_TIMEOUT"
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            error = f"visualization provider call failed (attempt {attempt}): {exc}"
            logger.warning("Design visualization: %s", error)
            return None, error, "VISUALIZATION_PROVIDER_ERROR"


class FalKontextVisualizationProvider(DesignVisualizationProvider):
    """Phase 4.1, section 15-19: selected after the provider spike as the
    only one of Aliyun/OpenAI/Gemini/fal.ai that actually returned a usable
    generated image on the accounts available (Aliyun: empty payload on
    every image-capable model; OpenAI: valid key, no billing credits;
    Gemini: valid key, image models on a zero-quota free tier). fal.ai's
    `fal-ai/flux-pro/kontext` is a single, narrow primitive -- image +
    instruction in, image out -- that every staged operation (material
    prep, base composition, targeted design edit) composes on top of
    (section 16), rather than a bespoke method per stage.

    Implements `DesignVisualizationProvider.generate()` for drop-in
    compatibility with the existing one-shot Phase 4 pipeline, AND exposes
    `edit_image()` directly for the staged pipeline -- composition, not a
    parallel class hierarchy (section 16)."""

    def edit_image(self, image: ReferenceImage, prompt: str) -> VisualizationProviderResult:
        """The one primitive: an existing image + a text instruction ->
        a new image. Bounded timeout, no retry loop beyond what the caller
        orchestrates (a staged pipeline retries at the STAGE level, not by
        looping this call -- section 17)."""
        settings = get_settings()
        api_key = settings.fal_api_key
        if not api_key:
            return VisualizationProviderResult(
                images=[], error="FAL_KEY is not configured", error_code="VISUALIZATION_PROVIDER_ERROR"
            )

        b64 = base64.b64encode(image.data).decode()
        data_uri = f"data:{image.content_type};base64,{b64}"
        t0 = time.monotonic()
        try:
            response = httpx.post(
                f"https://fal.run/{settings.fal_edit_model}",
                headers={"Authorization": f"Key {api_key}"},
                json={"prompt": prompt, "image_url": data_uri},
                timeout=settings.fal_timeout_s,
            )
            response.raise_for_status()
            body = response.json()
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
        except httpx.TimeoutException as exc:
            error = f"fal.ai did not respond within {settings.fal_timeout_s}s: {exc}"
            logger.warning("Design visualization: %s", error)
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error=error, error_code="VISUALIZATION_PROVIDER_TIMEOUT",
            )
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            error = f"fal.ai call failed: {exc}"
            logger.warning("Design visualization: %s", error)
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error=error, error_code="VISUALIZATION_PROVIDER_ERROR",
            )

        image_infos = body.get("images") or []
        if not image_infos:
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=latency_ms,
                error="fal.ai returned no image", error_code="VISUALIZATION_OUTPUT_EMPTY",
            )

        images: list[GeneratedImage] = []
        for info in image_infos:
            url = info.get("url")
            if not url:
                continue
            img_resp = httpx.get(url, timeout=settings.fal_timeout_s)
            img_resp.raise_for_status()
            content_type = info.get("content_type", "image/jpeg")
            images.append(GeneratedImage(data=img_resp.content, content_type=content_type))

        if not images:
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=latency_ms,
                error="fal.ai response had no downloadable image", error_code="VISUALIZATION_OUTPUT_EMPTY",
            )
        return VisualizationProviderResult(images=images, attempts=1, latency_ms=latency_ms)

    def generate(self, request: VisualizationProviderRequest) -> VisualizationProviderResult:
        """One-shot compatibility path for the existing Phase 4 pipeline --
        uses only the first reference image (fal.ai's kontext primitive
        takes one image), same as every staged call. Always makes exactly
        ONE generation call regardless of `request.count` -- one request
        must never silently fan out into multiple paid generations, and a
        single real image must never be duplicated and reported as several
        distinct visualizations (Phase 4 finalization, section 5-6)."""
        if not request.reference_images:
            return VisualizationProviderResult(
                images=[], error="no reference image supplied", error_code="VISUALIZATION_PROVIDER_ERROR"
            )
        return self.edit_image(request.reference_images[0], request.prompt)


class GeminiVisualizationProvider(DesignVisualizationProvider):
    """Phase 4.1 Gemini spike (sections 2-3): a bounded experiment to
    answer "can Gemini alone satisfy Phase 4" before spending on fal.ai's
    top-up. Talks to Gemini's `generateContent` REST API directly (Gemini
    has no OpenAI-compatible chat endpoint) -- inline base64 image parts in
    the request, `inlineData`/`inline_data` image parts expected back in
    the response. Same single `edit_image` primitive as fal.ai, so the
    staged pipeline (Stage 1/2/3) is unchanged regardless of which
    provider is selected (section 31-32)."""

    def edit_image(self, image: ReferenceImage, prompt: str) -> VisualizationProviderResult:
        settings = get_settings()
        api_key = settings.gemini_api_key
        if not api_key:
            return VisualizationProviderResult(
                images=[], error="GEMINI_API_KEY is not configured", error_code="VISUALIZATION_PROVIDER_ERROR"
            )

        b64 = base64.b64encode(image.data).decode()
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": image.content_type, "data": b64}},
                    ]
                }
            ]
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_image_model}:generateContent"
        )
        t0 = time.monotonic()
        try:
            response = httpx.post(
                url, params={"key": api_key}, json=body, timeout=settings.gemini_timeout_s
            )
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            payload = response.json()
            if response.status_code != 200:
                error_info = payload.get("error", {})
                error = f"Gemini call failed ({response.status_code}): {error_info.get('message', payload)}"
                logger.warning("Design visualization: %s", error)
                error_code = "VISUALIZATION_PROVIDER_QUOTA" if response.status_code == 429 else (
                    "VISUALIZATION_PROVIDER_ERROR"
                )
                return VisualizationProviderResult(
                    images=[], attempts=1, latency_ms=latency_ms, error=error, error_code=error_code
                )
        except httpx.TimeoutException as exc:
            error = f"Gemini did not respond within {settings.gemini_timeout_s}s: {exc}"
            logger.warning("Design visualization: %s", error)
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error=error, error_code="VISUALIZATION_PROVIDER_TIMEOUT",
            )
        except httpx.HTTPError as exc:
            error = f"Gemini call failed: {exc}"
            logger.warning("Design visualization: %s", error)
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error=error, error_code="VISUALIZATION_PROVIDER_ERROR",
            )

        images = _extract_gemini_images(payload)
        if not images:
            return VisualizationProviderResult(
                images=[], attempts=1, latency_ms=latency_ms,
                error="Gemini returned no image payload", error_code="VISUALIZATION_OUTPUT_EMPTY",
            )
        return VisualizationProviderResult(images=images, attempts=1, latency_ms=latency_ms)

    def generate(self, request: VisualizationProviderRequest) -> VisualizationProviderResult:
        """Always makes exactly ONE generation call regardless of
        `request.count` -- see `FalKontextVisualizationProvider.generate()`
        for why (Phase 4 finalization, section 5-6)."""
        if not request.reference_images:
            return VisualizationProviderResult(
                images=[], error="no reference image supplied", error_code="VISUALIZATION_PROVIDER_ERROR"
            )
        return self.edit_image(request.reference_images[0], request.prompt)


def _extract_gemini_images(payload: dict) -> list[GeneratedImage]:
    """Handles both `inlineData` (Gemini's documented REST response key)
    and `inline_data` (defensive, in case of proto-JSON snake_case)."""
    images: list[GeneratedImage] = []
    for candidate in payload.get("candidates") or []:
        parts = (candidate.get("content") or {}).get("parts") or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline:
                continue
            data = inline.get("data")
            mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
            if data:
                images.append(GeneratedImage(data=base64.b64decode(data), content_type=mime_type))
    return images


def provider_label(provider: object) -> str:
    """Single canonical name-lookup for a provider instance -- used for
    both result metadata and cost-estimate lookup (section 7 cost
    telemetry), so the two never drift out of sync."""
    if isinstance(provider, MockDesignVisualizationProvider):
        return "mock"
    if isinstance(provider, GeminiVisualizationProvider):
        return "gemini"
    if isinstance(provider, FalKontextVisualizationProvider):
        return "fal"
    if isinstance(provider, OpenAICompatibleDesignVisualizationProvider):
        return "openai_compatible"
    return "unknown"


def estimated_cost_per_image_usd(label: str) -> float | None:
    """An ESTIMATE from each provider's own observed/published per-image
    pricing (section 7/23) -- never a real billed amount; none of the
    evaluated providers expose a per-image usage API."""
    settings = get_settings()
    if label == "gemini":
        return settings.gemini_estimated_cost_per_image_usd
    if label == "fal":
        return settings.fal_estimated_cost_per_image_usd
    return None


def get_design_visualization_provider() -> DesignVisualizationProvider:
    """The MVP default is Gemini (validated real-image acceptance -- see
    docs/visualization-engine.md); Aliyun remains selectable explicitly but
    is not preferred by "auto" since it was never proven to return usable
    images on the accounts investigated."""
    settings = get_settings()
    mode = (settings.visualization_provider or "auto").strip().lower()

    if mode == "mock":
        return MockDesignVisualizationProvider()
    if mode == "fal":
        return FalKontextVisualizationProvider()
    if mode == "gemini":
        return GeminiVisualizationProvider()
    if mode in ("live", "openai_compatible", "alibaba", "aliyun", "dashscope"):
        return OpenAICompatibleDesignVisualizationProvider()

    # auto: prefer Gemini (MVP provider) when configured, then fal, then
    # Aliyun only if explicitly enabled, otherwise mock -- never silently
    # fail with no provider at all.
    if settings.gemini_api_key:
        return GeminiVisualizationProvider()
    if settings.fal_api_key:
        return FalKontextVisualizationProvider()
    if settings.visualization_enabled:
        return OpenAICompatibleDesignVisualizationProvider()
    return MockDesignVisualizationProvider()


def get_edit_capable_provider() -> ImageEditCapableProvider:
    """Phase 4.1: the provider used by the staged pipeline (Stage 1 prep,
    Stage 2 composition, Stage 3 targeted edits) -- all three compose on
    top of ONE `edit_image` primitive (section 16). fal.ai and Gemini are
    both wired in behind this same capability so the spike can compare
    them without touching the staged pipeline itself (section 31-32).
    Aliyun's `qwen-image-edit` is not routed here (it doesn't implement
    this capability) until it's proven functional (section 28)."""
    settings = get_settings()
    mode = (settings.visualization_provider or "auto").strip().lower()

    if mode == "mock":
        return MockDesignVisualizationProvider()
    if mode == "fal":
        return FalKontextVisualizationProvider()
    if mode == "gemini":
        return GeminiVisualizationProvider()

    # auto: prefer whichever live provider has a credential configured,
    # mock otherwise -- never silently fail with no provider at all.
    if settings.gemini_api_key:
        return GeminiVisualizationProvider()
    if settings.fal_api_key:
        return FalKontextVisualizationProvider()
    return MockDesignVisualizationProvider()


# --- Visual validation provider (section 16) -------------------------------


@dataclass
class ValidationProviderResult:
    observation: GeneratedImageObservation | None
    attempts: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    error_code: str | None = None


class GeneratedImageValidator(ABC):
    @abstractmethod
    def analyze(self, image_bytes: bytes, content_type: str = "image/png") -> ValidationProviderResult:
        """Returns a compact `GeneratedImageObservation` -- "what is visibly
        present," never a judgement of quality. Never raises."""


class MockGeneratedImageValidator(GeneratedImageValidator):
    """Deterministic default -- returns an entirely unknown observation
    (never a fabricated match) so validation degrades to UNKNOWN rather
    than a false PASS when no live vision model is configured."""

    def analyze(self, image_bytes: bytes, content_type: str = "image/png") -> ValidationProviderResult:
        return ValidationProviderResult(
            observation=GeneratedImageObservation(reason="Mock validator -- no real visual analysis performed."),
            attempts=1,
        )


_VALIDATION_SYSTEM_PROMPT = (
    "You are inspecting a single generated fashion-design concept image. Report ONLY what is visibly present "
    "-- never whether the design is good, never whether it is aesthetically pleasing. Respond with ONLY a "
    "single JSON object: {\"garment_subject\": str|null, \"neckline\": str|null, \"sleeve_length\": str|null, "
    "\"sleeve_style\": str|null, \"dupatta_present\": bool|null, \"dominant_color\": str|null, "
    "\"surface_density\": \"none\"|\"sparse\"|\"moderate\"|\"dense\"|null, \"border_present\": bool|null, "
    "\"transparency\": \"opaque\"|\"semi_sheer\"|\"sheer\"|null, \"reason\": str}. Use null for anything you "
    "cannot clearly tell from the image -- never guess. No prose outside the JSON, no markdown fences."
)


class OpenAICompatibleGeneratedImageValidator(GeneratedImageValidator):
    """Reuses the Phase 3 vision-understanding provider's model/credential
    by default (section 16: "reuse the vision-provider architecture where
    appropriate") -- a separate call from generation, so validation and
    generation stay independently swappable."""

    def analyze(self, image_bytes: bytes, content_type: str = "image/png") -> ValidationProviderResult:
        settings = get_settings()
        model = settings.visualization_validation_model or settings.vision_model
        api_key = settings.visualization_api_key or settings.vision_api_key or settings.llm_api_key
        b64 = base64.b64encode(image_bytes).decode()
        messages = [
            {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is visibly present in this generated design image?"},
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}},
                ],
            },
        ]

        deadline = time.monotonic() + _VALIDATION_TOTAL_BUDGET_S
        latency_ms = 0.0
        error: str | None = None
        error_code: str | None = None
        attempt = 0

        for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 2.0:
                error = f"visual validation time budget exhausted after {attempt - 1} attempt(s)"
                error_code = "VALIDATION_PROVIDER_TIMEOUT"
                break

            call_timeout = min(_VALIDATION_CALL_TIMEOUT_S, remaining)
            t0 = time.monotonic()
            content, call_error, call_error_code = self._call_once(
                messages, settings, model, api_key, attempt, call_timeout
            )
            latency_ms += (time.monotonic() - t0) * 1000
            if content is None:
                error, error_code = call_error, call_error_code
                continue

            try:
                parsed = json.loads(content)
                observation = GeneratedImageObservation(**parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                error = f"invalid validation output (attempt {attempt}): {exc}"
                error_code = "VALIDATION_OUTPUT_INVALID"
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {"role": "user", "content": f"That failed to parse ({exc}). Respond with ONLY JSON."}
                )
                continue

            return ValidationProviderResult(
                observation=observation, attempts=attempt, latency_ms=round(latency_ms, 1)
            )

        return ValidationProviderResult(
            observation=None,
            attempts=attempt,
            latency_ms=round(latency_ms, 1),
            error=error or "visual validation returned no usable observation",
            error_code=error_code or "VALIDATION_PROVIDER_ERROR",
        )

    def _call_once(
        self, messages: list[dict], settings, model: str, api_key: str, attempt: int, timeout_s: float
    ) -> tuple[str | None, str | None, str | None]:
        try:
            response = httpx.post(
                f"{settings.vision_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 400,
                    "enable_thinking": False,
                    "response_format": {"type": "json_object"},
                },
                timeout=timeout_s,
            )
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"]["content"], None, None
        except httpx.TimeoutException as exc:
            error = f"visual validation did not respond within {timeout_s:.0f}s (attempt {attempt}): {exc}"
            logger.warning("Visual validation: %s", error)
            return None, error, "VALIDATION_PROVIDER_TIMEOUT"
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            error = f"visual validation call failed (attempt {attempt}): {exc}"
            logger.warning("Visual validation: %s", error)
            return None, error, "VALIDATION_PROVIDER_ERROR"


def get_generated_image_validator() -> GeneratedImageValidator:
    settings = get_settings()
    mode = (settings.visualization_provider or "auto").strip().lower()

    if mode == "mock":
        return MockGeneratedImageValidator()
    if mode in ("live", "openai_compatible", "alibaba", "aliyun", "dashscope"):
        return OpenAICompatibleGeneratedImageValidator()

    if not settings.visualization_enabled:
        return MockGeneratedImageValidator()
    return OpenAICompatibleGeneratedImageValidator()
