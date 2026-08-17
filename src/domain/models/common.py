"""Shared base types for every domain model in the kernel."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Base for every domain model: unknown fields fail loudly instead of
    being silently dropped, and enum fields serialize as their plain value."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Range(DomainModel):
    min: float
    max: float

    def midpoint(self) -> float:
        return (self.min + self.max) / 2

    def contains(self, value: float) -> bool:
        return self.min <= value <= self.max


class Confidence(DomainModel):
    """A 0-1 score plus a human label. Every kernel output that involves an
    assumption or an inference carries one of these rather than presenting a
    guess as fact."""

    score: float = Field(ge=0.0, le=1.0)
    label: str  # high | medium | low

    @classmethod
    def of(cls, score: float) -> Confidence:
        score = min(max(score, 0.0), 1.0)
        if score >= 0.75:
            label = "high"
        elif score >= 0.45:
            label = "medium"
        else:
            label = "low"
        return cls(score=round(score, 2), label=label)
