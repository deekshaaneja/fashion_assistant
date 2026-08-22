"""mock_brain: the deterministic slot-extraction helpers `MockConversationProvider`
uses to decide WHAT a `DESIGN_GENERATION`/`DESIGN_MODIFICATION`/
`VISUALIZATION_REQUEST` turn should do, with zero network call. This is
what lets all 6 required scenario fixtures (product brief section 47) run
end-to-end offline -- the mock needs a complete-enough "brain," not just
tool-execution stubbing.
"""
from __future__ import annotations

import re

from src.domain.enums import NecklineType
from src.domain.models.session import DesignSession

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_DIGIT_PATTERN = re.compile(r"\b(\d+)\b")
_NECKLINE_VALUES = {member.value for member in NecklineType}


def extract_count(message: str, default: int = 3) -> int:
    lowered = message.lower()
    for word, n in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return n
    match = _DIGIT_PATTERN.search(message)
    if match:
        return min(5, max(1, int(match.group(1))))
    return default


def extract_design_change(message: str) -> dict | None:
    """Best-effort extraction of a `{component, operation, value}` patch
    from an explicit modification instruction -- `base_version_id` is
    deliberately NOT produced here; it is always filled in by the
    orchestrator from session state, never authored by the model/mock."""
    lowered = message.lower()

    if "neckline" in lowered:
        for value in _NECKLINE_VALUES:
            token = value.replace("_", " ")
            if token in lowered:
                return {"component": "neckline", "operation": "set", "value": {"type": value}}

    if "sleeve" in lowered:
        if "sheer" in lowered:
            return {"component": "sleeves", "operation": "set", "value": {"sheer": True}}
        if "not sheer" in lowered or "opaque" in lowered:
            return {"component": "sleeves", "operation": "set", "value": {"sheer": False}}

    return None


def extract_visualization_targets(message: str, session: DesignSession) -> list[str]:
    lowered = message.lower()
    if "all three" in lowered or "all of them" in lowered or "each of" in lowered:
        return list(session.last_design_batch)
    if session.selected_design_family_id:
        return [session.selected_design_family_id]
    return list(session.last_design_batch[:1])
