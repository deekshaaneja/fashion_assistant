from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_dna import DesignDNA
from src.fashion_engine.design.dna import derive_target_dna


def test_distance_is_zero_for_identical_dna():
    dna = DesignDNA(traditional_contemporary=0.3, soft_architectural=0.8)
    assert dna.distance(dna) == 0.0


def test_distance_is_positive_for_different_dna():
    a = DesignDNA(traditional_contemporary=0.1)
    b = DesignDNA(traditional_contemporary=0.9)
    assert a.distance(b) > 0.0


def test_derive_target_dna_contemporary_tag_leans_contemporary():
    brief = ClientBrief(desired_aesthetic=["contemporary"])
    target = derive_target_dna(brief)
    assert target.traditional_contemporary > 0.5


def test_derive_target_dna_traditional_tag_leans_traditional():
    brief = ClientBrief(desired_aesthetic=["traditional"])
    target = derive_target_dna(brief)
    assert target.traditional_contemporary < 0.5


def test_explicit_lean_overrides_tag_derived_value():
    brief = ClientBrief(desired_aesthetic=["contemporary"], traditional_contemporary_lean=0.05)
    target = derive_target_dna(brief)
    assert target.traditional_contemporary == 0.05


def test_no_signal_produces_neutral_dna():
    target = derive_target_dna(ClientBrief())
    assert target == DesignDNA()
