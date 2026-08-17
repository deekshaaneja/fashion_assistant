"""LanguageModelProvider: the only place an LLM touches the kernel's output,
and only for prose explanation -- never for arithmetic, scoring, feasibility,
or fabric/silhouette compatibility (section 2 of the product brief). Disabled
by default; every tool in the kernel is fully functional without it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from src.providers.settings import get_settings


class LanguageModelProvider(ABC):
    """Abstract boundary so the kernel never depends on a specific LLM
    vendor/endpoint -- only on this narrow "explain a set of facts" contract."""

    @abstractmethod
    def explain(self, facts_prompt: str, fallback: str) -> str:
        """Returns LLM prose grounded in `facts_prompt`, or `fallback`
        verbatim if the provider is disabled or the call fails for any
        reason. Never raises."""


class NullLanguageModelProvider(LanguageModelProvider):
    """The default provider: always returns the deterministic fallback
    untouched. Proves the kernel needs no LLM to be useful."""

    def explain(self, facts_prompt: str, fallback: str) -> str:
        return fallback


class OpenAICompatibleProvider(LanguageModelProvider):
    """Talks to any OpenAI-compatible /chat/completions endpoint (Ollama,
    Aliyun DashScope's compatible-mode, OpenAI itself, etc.) via plain
    httpx -- no SDK dependency."""

    def explain(self, facts_prompt: str, fallback: str) -> str:
        settings = get_settings()
        try:
            response = httpx.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {},
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You explain already-computed fashion recommendations in plain, warm "
                                "language. Base your answer only on the facts given -- do not invent new "
                                "scores, numbers, or facts, and do not change any classification or number."
                            ),
                        },
                        {"role": "user", "content": facts_prompt},
                    ],
                    "temperature": 0.3,
                },
                timeout=settings.request_timeout_s,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return content.strip() or fallback
        except Exception:
            return fallback


def get_language_model_provider() -> LanguageModelProvider:
    settings = get_settings()
    if not settings.llm_enabled:
        return NullLanguageModelProvider()
    return OpenAICompatibleProvider()
