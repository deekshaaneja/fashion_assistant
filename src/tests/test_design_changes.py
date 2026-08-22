from __future__ import annotations

import pytest

from src.agent.design_changes import apply_design_change, register_design_proposal
from src.domain.models.session import DesignChange, DesignSession, FabricRef
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage, generate_design_directions_from_images
from src.providers.settings import get_settings
from src.tests.conftest import make_synthetic_fabric_image


@pytest.fixture(autouse=True)
def _deterministic_providers(monkeypatch):
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "template")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _session_with_root_design():
    images = [UploadedFabricImage(image_id="img1", data=make_synthetic_fabric_image())]
    result = generate_design_directions_from_images(images, fabric_name_hint="organza", count=1)
    proposal = result.design_directions.designs[0]

    session = DesignSession()
    session.fabric_refs.append(
        FabricRef(fabric_id="f1", fabric_name="organza", source="text_declared", declared_properties=None)
    )
    node = register_design_proposal(session, proposal)
    return session, node


def test_apply_valid_neckline_change_creates_new_immutable_version():
    session, base = _session_with_root_design()
    change = DesignChange(base_version_id=base.version_id, component="neckline", operation="set", value={"type": "square"})

    result = apply_design_change(session, change)

    assert result.ok, result.rejection_issues
    assert result.new_version.proposal.neckline.type == "square"
    assert result.new_version.parent_version_id == base.version_id
    # the base version is untouched -- immutability
    reloaded_base = session.designs[base.design_family_id][0]
    assert reloaded_base.proposal.neckline.type == base.proposal.neckline.type
    assert session.current_version_id[base.design_family_id] == result.new_version.version_id


def test_apply_sheer_sleeves_change():
    session, base = _session_with_root_design()
    change = DesignChange(base_version_id=base.version_id, component="sleeves", operation="set", value={"sheer": True})

    result = apply_design_change(session, change)

    assert result.ok, result.rejection_issues
    assert result.new_version.proposal.sleeves.sheer is True


def test_incoherent_construction_change_is_rejected_and_base_untouched():
    session, base = _session_with_root_design()
    # A DRAMATIC flare_construction with a MINIMAL flare_level is a genuine
    # structural contradiction -- check_coherence must reject it.
    change = DesignChange(
        base_version_id=base.version_id,
        component="construction",
        operation="set",
        value={"flare_construction": "dramatic", "flare_level": "minimal"},
    )

    result = apply_design_change(session, change)

    assert not result.ok
    assert any("flare_construction" in issue for issue in result.rejection_issues)
    assert len(session.designs[base.design_family_id]) == 1  # nothing committed


def test_incomplete_replace_value_is_rejected_not_raised():
    session, base = _session_with_root_design()
    change = DesignChange(
        base_version_id=base.version_id, component="neckline", operation="replace", value={"type": "square"}
    )  # missing required `rationale` for a full replace

    result = apply_design_change(session, change)

    assert not result.ok
    assert result.rejection_issues


def test_unknown_base_version_is_rejected():
    session, _base = _session_with_root_design()
    change = DesignChange(base_version_id="does-not-exist", component="neckline", operation="set", value={"type": "square"})

    result = apply_design_change(session, change)

    assert not result.ok
    assert "unknown design version" in result.rejection_issues[0]


def test_successive_modifications_do_not_accumulate_duplicate_risks():
    session, base = _session_with_root_design()
    change1 = DesignChange(base_version_id=base.version_id, component="neckline", operation="set", value={"type": "square"})
    v2 = apply_design_change(session, change1).new_version
    change2 = DesignChange(base_version_id=v2.version_id, component="sleeves", operation="set", value={"sheer": True})
    v3 = apply_design_change(session, change2).new_version

    assert v3.proposal.risks == base.proposal.risks
