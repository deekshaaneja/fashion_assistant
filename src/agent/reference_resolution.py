"""reference_resolution: deterministic resolution of natural-language
references ("option 2", "the previous design", "same fabric") against
`DesignSession` state (product brief section 12-13) -- never re-asked of
the user when the session already makes the reference unambiguous.
"""
from __future__ import annotations

import re

from src.domain.models.session import DesignSession

_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_NUMBER_PATTERN = re.compile(r"\b(?:option|number|design)\s*#?\s*(\d+)\b", re.I)
_ORDINAL_PATTERN = re.compile(r"\bthe\s+(first|second|third|fourth|fifth)\b", re.I)


def resolve_design_selection(message: str, family_ids_in_order: list[str]) -> str | None:
    """Resolves 'option 2' / 'number 2' / 'the second one' to a
    `design_family_id` from a batch given in presentation order."""
    match = _NUMBER_PATTERN.search(message)
    index: int | None = None
    if match:
        index = int(match.group(1))
    else:
        ordinal_match = _ORDINAL_PATTERN.search(message)
        if ordinal_match:
            index = _ORDINAL_WORDS.get(ordinal_match.group(1).lower())
    if index is None or index < 1 or index > len(family_ids_in_order):
        return None
    return family_ids_in_order[index - 1]


def resolve_current_design_reference(session: DesignSession) -> str | None:
    """Resolves an implicit reference to 'the current design' -- the
    session's selected design family, if one exists."""
    return session.selected_design_family_id
