from __future__ import annotations

from src.agent.intent import classify_intent
from src.domain.models.session import DesignSession


def _classify(message: str, has_images: bool = False) -> str:
    return classify_intent(message, DesignSession(), has_images=has_images)


def test_images_attached_always_classify_as_fabric_analysis():
    assert _classify("here you go", has_images=True) == "FABRIC_ANALYSIS"


def test_show_me_is_visualization_request():
    assert _classify("Show me.") == "VISUALIZATION_REQUEST"


def test_undo_and_redo():
    assert _classify("Undo that.") == "UNDO"
    assert _classify("Redo please.") == "REDO"


def test_start_over_is_reset():
    assert _classify("Let's start over.") == "RESET"


def test_option_selection():
    assert _classify("I like number 2.") == "DESIGN_SELECTION"
    assert _classify("The second one, please.") == "DESIGN_SELECTION"


def test_modification_phrasing():
    assert _classify("Make the neckline square.") == "DESIGN_MODIFICATION"
    assert _classify("Make the sleeves sheer.") == "DESIGN_MODIFICATION"


def test_generation_request():
    assert _classify("Give me three options.") == "DESIGN_GENERATION"


def test_unmatched_message_falls_back_to_question():
    assert _classify("What do you think about silk brocade in general?") in ("QUESTION", "SILHOUETTE_RECOMMENDATION")
