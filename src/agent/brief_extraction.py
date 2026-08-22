"""brief_extraction: deterministic, best-effort extraction of client-brief
signals from free text (product brief section 21) -- never a giant NLU
model, just the keyword mapping needed to keep the client brief structured
rather than buried in conversation transcript. Applied on every turn,
independent of intent, so a message like "It's for a client's engagement,
elegant and contemporary" updates `session.client_brief`/`fashion_context`
even though its primary intent is something else.
"""
from __future__ import annotations

from src.domain.enums import Occasion
from src.domain.models.session import DesignSession

_OCCASION_KEYWORDS: dict[str, Occasion] = {
    "engagement": Occasion.ENGAGEMENT,
    "wedding guest": Occasion.WEDDING_GUEST,
    "wedding": Occasion.WEDDING_GUEST,
    "reception": Occasion.RECEPTION,
    "festive": Occasion.FESTIVE,
    "cocktail": Occasion.COCKTAIL,
    "daytime": Occasion.DAYTIME,
    "evening": Occasion.EVENING,
}

_AESTHETIC_KEYWORDS = (
    "elegant", "contemporary", "traditional", "modern", "romantic", "minimal", "bold", "understated",
)


def apply_brief_signals(session: DesignSession, message: str) -> None:
    lowered = message.lower()

    for phrase, occasion in _OCCASION_KEYWORDS.items():
        if phrase in lowered:
            session.fashion_context = session.fashion_context.model_copy(update={"occasion": occasion})
            session.client_brief = session.client_brief.model_copy(update={"occasion": occasion})
            break

    tags = [tag for tag in _AESTHETIC_KEYWORDS if tag in lowered]
    if tags:
        merged = list(dict.fromkeys([*session.client_brief.desired_aesthetic, *tags]))
        session.client_brief = session.client_brief.model_copy(update={"desired_aesthetic": merged})