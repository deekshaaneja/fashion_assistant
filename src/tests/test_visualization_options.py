"""Phase 4 finalization, section 24: MVP policy is exactly one
visualization per request -- enforced at the domain/request-validation
layer so a rejected request never reaches a provider at all."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.models.visualization import VisualizationOptions


def test_count_one_is_accepted():
    options = VisualizationOptions(count=1)
    assert options.count == 1


def test_count_defaults_to_one():
    assert VisualizationOptions().count == 1


def test_count_greater_than_one_is_rejected():
    with pytest.raises(ValidationError, match="MULTIPLE_VISUALIZATIONS_NOT_SUPPORTED"):
        VisualizationOptions(count=2)


def test_count_zero_is_rejected():
    with pytest.raises(ValidationError, match="MULTIPLE_VISUALIZATIONS_NOT_SUPPORTED"):
        VisualizationOptions(count=0)
