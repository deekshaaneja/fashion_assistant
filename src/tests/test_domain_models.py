from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.models.common import Confidence, Range


def test_domain_models_reject_unknown_fields():
    from src.domain.models.fabric_analysis import FabricObservation

    with pytest.raises(ValidationError):
        FabricObservation(fabric_name="silk", not_a_real_field=True)


def test_range_midpoint_and_contains():
    r = Range(min=2.0, max=4.0)
    assert r.midpoint() == 3.0
    assert r.contains(3.0)
    assert not r.contains(5.0)


def test_confidence_labels():
    assert Confidence.of(0.9).label == "high"
    assert Confidence.of(0.5).label == "medium"
    assert Confidence.of(0.1).label == "low"


def test_confidence_clamps_out_of_range_scores():
    assert Confidence.of(1.5).score == 1.0
    assert Confidence.of(-0.5).score == 0.0
