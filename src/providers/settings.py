"""Environment-driven settings. The LLM is optional everywhere; every tool in
the kernel is fully functional with it disabled (the default)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_enabled: bool = Field(default=False, alias="LLM_ENABLED")
    llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="qwen2.5:7b-instruct", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    request_timeout_s: int = Field(default=30, alias="REQUEST_TIMEOUT_S")

    # "auto" (default) = llm_enabled decides template vs. live, matching every
    # other provider in the kernel. "mock"/"template" force a specific
    # deterministic Phase 2 design-generation provider regardless of
    # llm_enabled -- "mock" in particular lets the generate-design-directions
    # endpoint be tested immediately, independent of any external model.
    # "live" / "openai_compatible" / "alibaba" / "aliyun" / "dashscope" are
    # all the same thing -- OpenAICompatibleDesignGenerationProvider, which
    # is what actually talks to Aliyun DashScope's compatible-mode endpoint
    # per LLM_BASE_URL/LLM_MODEL/LLM_API_KEY -- accepted as aliases so the
    # value can name the real provider being called rather than a generic
    # label.
    design_generation_provider: str = Field(default="auto", alias="DESIGN_GENERATION_PROVIDER")

    # Phase 2 performance fix -- these apply ONLY to design generation, never
    # to Phase 1's LanguageModelProvider.explain() calls (no global thinking
    # toggle). Default thinking OFF: empirically, Qwen3's default "thinking"
    # mode burns the large majority of output tokens on internal reasoning
    # even for trivial prompts (see docs/design-engine.md), which is the
    # dominant cause of the generate-design-directions timeout. Can be
    # flipped back on later to A/B quality vs. latency.
    design_generation_thinking: bool = Field(default=False, alias="DESIGN_GENERATION_THINKING")
    # A bound on live-provider output length -- the model-facing schema is
    # now small (creative fields only, section 3), so a single candidate's
    # response fits comfortably well under this.
    design_generation_max_tokens: int = Field(default=1200, alias="DESIGN_GENERATION_MAX_TOKENS")

    # Multi-direction generation fix: for count>1, each direction is its own
    # independent live call -- a partial failure (e.g. 2 of 3 succeed) is
    # returned AS-IS by default, never silently backfilled with template
    # designs (that would contaminate a live design-quality benchmark).
    # Flip this on to explicitly opt into filling the missing slot(s) with
    # the deterministic template provider instead of returning fewer designs.
    design_generation_template_backfill: bool = Field(
        default=False, alias="DESIGN_GENERATION_TEMPLATE_BACKFILL"
    )

    # Phase 3 -- visual fabric intelligence. Separate from LLM_* because the
    # vision-capable model is a different model than the text model
    # (qwen3.7-plus does NOT accept images -- empirically confirmed; see
    # docs/vision-engine.md). "auto" (default) = vision_enabled decides
    # mock vs. live, matching every other provider in the kernel.
    vision_enabled: bool = Field(default=False, alias="VISION_ENABLED")
    vision_provider: str = Field(default="auto", alias="VISION_PROVIDER")
    vision_base_url: str = Field(default="http://localhost:11434/v1", alias="VISION_BASE_URL")
    vision_model: str = Field(default="qwen3-vl-plus", alias="VISION_MODEL")
    # Empty by default -- reuse LLM_API_KEY rather than duplicating a secret
    # (section 22) unless a distinct vision credential is explicitly given.
    vision_api_key: str = Field(default="", alias="VISION_API_KEY")
    vision_max_tokens: int = Field(default=1500, alias="VISION_MAX_TOKENS")
    vision_timeout_s: int = Field(default=25, alias="VISION_TIMEOUT_S")

    # Phase 4 -- design visualization. Separate from VISION_*/LLM_* because
    # the image-GENERATION model is a third, distinct model from both the
    # text model and the vision-UNDERSTANDING model (empirically confirmed:
    # `qwen-image-edit` is the reference-conditioned image-editing model
    # this account's DashScope gateway actually exposes -- see
    # docs/visualization-engine.md). "auto" (default) = visualization_enabled
    # decides mock vs. live, matching every other provider in the kernel.
    visualization_enabled: bool = Field(default=False, alias="VISUALIZATION_ENABLED")
    visualization_provider: str = Field(default="auto", alias="VISUALIZATION_PROVIDER")
    visualization_base_url: str = Field(
        default="http://localhost:11434/v1", alias="VISUALIZATION_BASE_URL"
    )
    visualization_model: str = Field(default="qwen-image-edit", alias="VISUALIZATION_MODEL")
    # Empty by default -- reuse LLM_API_KEY rather than duplicating a secret.
    visualization_api_key: str = Field(default="", alias="VISUALIZATION_API_KEY")
    # Section 11/50: this account's qwen-image-edit rejected a request with
    # 0 reference images and documented a 1-3 image limit -- kept
    # configurable rather than hardcoded in provider code.
    visualization_max_reference_images: int = Field(default=3, alias="VISUALIZATION_MAX_REFERENCE_IMAGES")
    visualization_timeout_s: int = Field(default=45, alias="VISUALIZATION_TIMEOUT_S")
    visualization_storage_dir: str = Field(
        default="artifacts/visualizations", alias="VISUALIZATION_STORAGE_DIR"
    )
    # A separate, smaller model for visual VALIDATION (analyzing a generated
    # image against the specification, section 16) -- reuses the Phase 3
    # vision-understanding model/credential by default rather than a new one.
    visualization_validation_model: str = Field(
        default="", alias="VISUALIZATION_VALIDATION_MODEL", description="blank = reuse VISION_MODEL"
    )
    # Phase 4 finalization: OFF by default. The real Gemini acceptance
    # experiment established that localized corrective editing is
    # unreliable, and the visual validator itself is only probabilistic --
    # neither is a safe trigger for an automatic second PAID generation
    # without explicit opt-in. When enabled, at most one corrective
    # generation is ever made (never unbounded).
    visualization_auto_correct: bool = Field(default=False, alias="VISUALIZATION_AUTO_CORRECT")

    # fal.ai -- evaluated during the Phase 4.1 provider spike (accepts
    # reference-conditioned image edits), but NOT required for MVP: the
    # Gemini real-image acceptance experiment (see docs/visualization-engine.md)
    # passed using the rebuild-per-version pattern alone. Kept configured
    # and available behind `ImageEditCapableProvider` for a future provider
    # that specifically needs localized in-place editing, never as the MVP
    # default.
    fal_api_key: str = Field(default="", alias="FAL_KEY")
    fal_edit_model: str = Field(default="fal-ai/flux-pro/kontext", alias="FAL_EDIT_MODEL")
    fal_timeout_s: int = Field(default=90, alias="FAL_TIMEOUT_S")
    fal_estimated_cost_per_image_usd: float = Field(default=0.04, alias="FAL_ESTIMATED_COST_PER_IMAGE_USD")

    # Gemini -- the MVP Phase 4 visualization provider (validated on the
    # real organza anchor: preserves fabric identity/motif/embroidery/
    # color/transparency, and correctly executes exact target design
    # geometry via the rebuild-per-version pattern -- see
    # docs/visualization-engine.md). `estimated_cost_per_image_usd` is an
    # ESTIMATE from the spike's observed cost, not a billed figure from a
    # provider usage API (Gemini doesn't expose one per-image).
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_image_model: str = Field(default="gemini-2.5-flash-image", alias="GEMINI_IMAGE_MODEL")
    gemini_timeout_s: int = Field(default=90, alias="GEMINI_TIMEOUT_S")
    gemini_estimated_cost_per_image_usd: float = Field(
        default=0.04, alias="GEMINI_ESTIMATED_COST_PER_IMAGE_USD"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
