from __future__ import annotations

from src.domain.models.fabric_vision import ImageRole
from src.fashion_engine.visualization.reference_selector import CandidateFabricImage, select_fabric_references


def _c(image_id, role, usable=True, duplicate_of=None):
    return CandidateFabricImage(image_id=image_id, role=role, usable=usable, duplicate_of=duplicate_of)


def test_full_view_and_close_up_prioritized_over_others():
    candidates = [
        _c("reverse", ImageRole.REVERSE),
        _c("full", ImageRole.FULL_VIEW),
        _c("close", ImageRole.CLOSE_UP),
        _c("unknown", ImageRole.UNKNOWN),
    ]
    selection = select_fabric_references(candidates, max_references=2, uses_border=False)
    selected_ids = [s.image_id for s in selection.selected]
    assert selected_ids == ["full", "close"]
    assert "reverse" in selection.excluded_image_ids
    assert "unknown" in selection.excluded_image_ids


def test_border_deprioritized_when_design_does_not_use_it():
    candidates = [_c("border", ImageRole.BORDER), _c("full", ImageRole.FULL_VIEW), _c("close", ImageRole.CLOSE_UP)]
    selection = select_fabric_references(candidates, max_references=2, uses_border=False)
    selected_ids = [s.image_id for s in selection.selected]
    assert "border" not in selected_ids
    assert selected_ids == ["full", "close"]


def test_border_prioritized_when_design_uses_it():
    candidates = [_c("reverse", ImageRole.REVERSE), _c("border", ImageRole.BORDER), _c("full", ImageRole.FULL_VIEW)]
    selection = select_fabric_references(candidates, max_references=2, uses_border=True)
    selected_ids = {s.image_id for s in selection.selected}
    assert selected_ids == {"border", "full"}


def test_unusable_and_duplicate_images_never_selected():
    candidates = [
        _c("bad", ImageRole.FULL_VIEW, usable=False),
        _c("dup", ImageRole.FULL_VIEW, duplicate_of="full"),
        _c("full", ImageRole.FULL_VIEW),
    ]
    selection = select_fabric_references(candidates, max_references=3, uses_border=False)
    selected_ids = [s.image_id for s in selection.selected]
    assert selected_ids == ["full"]
    assert "bad" in selection.excluded_image_ids
    assert "dup" in selection.excluded_image_ids


def test_selection_records_reason_and_max_references():
    candidates = [_c("full", ImageRole.FULL_VIEW)]
    selection = select_fabric_references(candidates, max_references=3, uses_border=False)
    assert selection.max_references == 3
    assert selection.selected[0].reason


def test_drape_deprioritized_when_construction_does_not_need_it():
    candidates = [_c("drape", ImageRole.DRAPE), _c("full", ImageRole.FULL_VIEW), _c("close", ImageRole.CLOSE_UP)]
    selection = select_fabric_references(
        candidates, max_references=2, uses_border=False, flare_construction_uses_drape=False
    )
    selected_ids = [s.image_id for s in selection.selected]
    assert "drape" not in selected_ids
