"""classify_intent: deterministic, keyword/regex-based intent classification
(product brief section 14). This is a defense-in-depth cross-check even in
live mode (a live `TurnDecision.intent` is never trusted blind -- see
`src/providers/agent.py`), and it is the WHOLE classification brain for
`MockConversationProvider`, which must drive every required test scenario
with zero network calls.
"""
from __future__ import annotations

import re

from src.domain.models.session import DesignSession, IntentType

_PATTERNS: tuple[tuple[IntentType, re.Pattern[str]], ...] = (
    ("UNDO", re.compile(r"\bundo\b", re.I)),
    ("REDO", re.compile(r"\bredo\b", re.I)),
    ("RESET", re.compile(r"\b(start over|reset|start again)\b", re.I)),
    (
        "VISUALIZATION_REQUEST",
        re.compile(r"\b(show me|render|visuali[sz]e|see (it|them|the design))\b", re.I),
    ),
    (
        "DESIGN_SELECTION",
        re.compile(
            r"\b(i like|i'?ll (take|go with)|option\s*#?\d+|number\s*#?\d+|the (first|second|third) one)\b",
            re.I,
        ),
    ),
    (
        "DESIGN_MODIFICATION",
        re.compile(
            r"\bmake (the|it)\b|\bchange the\b|\binstead\b|\bshould be\b|\bshould have\b",
            re.I,
        ),
    ),
    (
        "DESIGN_GENERATION",
        re.compile(r"\bgive me\b.*\b(option|design|direction)s?\b|\b(generate|create)\b.*\bdesigns?\b", re.I),
    ),
    ("DUPATTA_REQUEST", re.compile(r"\bdupatta\b", re.I)),
    ("DECORATION_REQUEST", re.compile(r"\bembroidery|embellishment|decoration\b", re.I)),
    ("COLORWAY_REQUEST", re.compile(r"\bcolor|colour|palette\b", re.I)),
    ("SILHOUETTE_RECOMMENDATION", re.compile(r"\bwhat (can|should) i make\b|\bsilhouette\b", re.I)),
    (
        "FABRIC_ANALYSIS",
        re.compile(r"\b(this is my fabric|here'?s (my|a|the) fabric|i have this fabric)\b", re.I),
    ),
)


def classify_intent(message: str, session: DesignSession, has_images: bool = False) -> IntentType:
    if has_images:
        return "FABRIC_ANALYSIS"
    for intent, pattern in _PATTERNS:
        if pattern.search(message):
            return intent
    return "QUESTION"
