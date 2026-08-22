from __future__ import annotations

import pytest

from src.domain.models.design_proposal import DesignProposal
from src.domain.models.session import (
    DesignChange,
    DesignSession,
    DesignVersionNode,
    FabricRef,
    StoredImageRef,
    children_of,
    current_node,
    find_version_node,
    new_id,
)
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


def _sample_proposal() -> DesignProposal:
    images = [UploadedFabricImage(image_id="img1", data=make_synthetic_fabric_image())]
    result = generate_design_directions_from_images(images, fabric_name_hint="organza", count=1)
    return result.design_directions.designs[0]


def test_session_round_trips_through_json():
    session = DesignSession()
    session.fabric_refs.append(
        FabricRef(
            fabric_id="f1", fabric_name="organza", source="image_analyzed",
            source_images=[StoredImageRef(uri="visualizations/x.jpg")],
        )
    )
    payload = session.model_dump_json()
    restored = DesignSession.model_validate_json(payload)
    assert restored.session_id == session.session_id
    assert restored.fabric_refs[0].fabric_name == "organza"


def test_version_tree_branching_via_parent_pointers():
    session = DesignSession()
    proposal = _sample_proposal()
    root = DesignVersionNode(version_id="D1-V1", design_family_id="D1", proposal=proposal)
    session.designs["D1"] = [root]
    session.current_version_id["D1"] = "D1-V1"

    branch_a = DesignVersionNode(
        version_id="D1-V2a", design_family_id="D1", parent_version_id="D1-V1", proposal=proposal
    )
    branch_b = DesignVersionNode(
        version_id="D1-V2b", design_family_id="D1", parent_version_id="D1-V1", proposal=proposal
    )
    session.designs["D1"].extend([branch_a, branch_b])

    children = children_of(session, "D1-V1")
    assert {c.version_id for c in children} == {"D1-V2a", "D1-V2b"}
    assert find_version_node(session, "D1-V2b") is branch_b
    assert current_node(session, "D1").version_id == "D1-V1"


def test_design_change_requires_known_component_literal():
    # component is a closed Literal -- an unknown component name fails
    # validation before it can ever reach the apply pipeline.
    try:
        DesignChange(base_version_id="D1-V1", component="hemline", operation="set", value={})
        raised = False
    except Exception:
        raised = True
    assert raised


def test_new_id_prefixes_are_stable():
    assert new_id("session").startswith("session_")
    assert new_id("D").startswith("D_")
