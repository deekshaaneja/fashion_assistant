from __future__ import annotations

from src.agent.reference_resolution import resolve_current_design_reference, resolve_design_selection
from src.domain.models.session import DesignSession


def test_resolves_numeric_option_reference():
    assert resolve_design_selection("I like number 2.", ["D1", "D2", "D3"]) == "D2"
    assert resolve_design_selection("option 3 please", ["D1", "D2", "D3"]) == "D3"


def test_resolves_ordinal_word_reference():
    assert resolve_design_selection("the second one", ["D1", "D2", "D3"]) == "D2"


def test_out_of_range_reference_returns_none():
    assert resolve_design_selection("number 9", ["D1", "D2", "D3"]) is None


def test_no_reference_returns_none():
    assert resolve_design_selection("I like this one a lot", ["D1", "D2", "D3"]) is None


def test_current_design_reference_uses_session_selection():
    session = DesignSession()
    assert resolve_current_design_reference(session) is None
    session.selected_design_family_id = "D2"
    assert resolve_current_design_reference(session) == "D2"
