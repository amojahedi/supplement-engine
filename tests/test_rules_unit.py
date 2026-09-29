"""Targeted unit tests for the engine's core safety behaviors.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

import pytest

from supplement_engine.rules import canonical, evaluate


def _canon(names):
    return [canonical(n) for n in names]


# --------------------------------------------------------------------------- #
# Escalation suppression
# --------------------------------------------------------------------------- #
def test_diabetes_escalation_suppresses_all(profiles):
    """P04: high HbA1c + symptoms -> refer, recommend nothing, no recs."""
    d = evaluate(profiles["P04"])
    assert d.refer_to_clinician
    assert d.recommend_nothing
    assert d.recommend == []
    assert d.priority_order == []


def test_thyroid_escalation_suppresses_all(profiles):
    """P22: high TSH + symptoms -> refer + recommend nothing."""
    d = evaluate(profiles["P22"])
    assert d.refer_to_clinician and d.recommend_nothing and not d.recommend


def test_high_ferritin_blocks_iron_and_suppresses(profiles):
    """P23: high ferritin -> block iron, refer, recommend nothing (block survives)."""
    d = evaluate(profiles["P23"])
    assert "iron" in _canon(b.supplement for b in d.block)
    assert d.refer_to_clinician and d.recommend_nothing and not d.recommend


def test_multideficiency_weightloss_escalates(profiles):
    """P29: severe multi-deficiency + unexplained weight loss -> refer, nothing."""
    d = evaluate(profiles["P29"])
    assert d.refer_to_clinician and d.recommend_nothing and not d.recommend


def test_ckd_ace_escalates(profiles):
    """P25: CKD + ACE inhibitor -> block K/Mg, refer, recommend nothing."""
    d = evaluate(profiles["P25"])
    blocked = _canon(b.supplement for b in d.block)
    assert "potassium" in blocked and "magnesium" in blocked
    assert d.refer_to_clinician and d.recommend_nothing


def test_methotrexate_folate_coupling_suppresses(profiles):
    """P14: methotrexate + low folate -> block self folate, refer, nothing."""
    d = evaluate(profiles["P14"])
    assert "folate" in _canon(b.supplement for b in d.block)
    assert d.refer_to_clinician and d.recommend_nothing and not d.recommend


def test_prediabetes_no_supplement_no_refer(profiles):
    """P15: prediabetes with no deficiency -> recommend nothing, no referral."""
    d = evaluate(profiles["P15"])
    assert d.recommend_nothing and not d.refer_to_clinician and not d.recommend


# --------------------------------------------------------------------------- #
# Near-boundary NO-trigger (must not false-positive)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pid", ["P03", "P12", "P19", "P26", "P30"])
def test_in_range_no_trigger(pid, profiles):
    d = evaluate(profiles[pid])
    assert d.recommend == []
    assert d.recommend_nothing
    assert not d.refer_to_clinician
    assert d.block == []


# --------------------------------------------------------------------------- #
# Age-aware interpretation
# --------------------------------------------------------------------------- #
def test_older_adult_b12_320_not_flagged(profiles):
    """P30: B12 320 in a 68-year-old is adequate; must not trigger."""
    d = evaluate(profiles["P30"])
    assert "vitamin_b12" not in _canon(r.supplement for r in d.recommend)


def test_older_adult_b12_340_not_flagged(profiles):
    """P12: B12 340 in a 72-year-old is adequate."""
    d = evaluate(profiles["P12"])
    assert d.recommend_nothing


# --------------------------------------------------------------------------- #
# B12-before-folate ordering (safety property)
# --------------------------------------------------------------------------- #
def test_b12_precedes_folate_when_both_recommended(profiles):
    """P21: both B12 and folate recommended -> B12 must be ordered first."""
    d = evaluate(profiles["P21"])
    order = _canon(d.priority_order)
    assert "vitamin_b12" in order and "folate" in order
    assert order.index("vitamin_b12") < order.index("folate")


def test_b12_before_folate_in_multideficiency(profiles):
    """P13: even amid several deficiencies, B12 must precede folate."""
    d = evaluate(profiles["P13"])
    order = _canon(d.priority_order)
    assert order.index("vitamin_b12") < order.index("folate")


# --------------------------------------------------------------------------- #
# Pregnancy: folate first
# --------------------------------------------------------------------------- #
def test_pregnancy_folate_first(profiles):
    """P05: pregnancy -> folate is the top priority."""
    d = evaluate(profiles["P05"])
    assert _canon(d.priority_order)[0] == "folate"


# --------------------------------------------------------------------------- #
# Priority is only surfaced on genuine conflicts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pid", ["P06", "P07", "P10", "P11"])
def test_single_recommendation_has_no_priority_order(pid, profiles):
    d = evaluate(profiles[pid])
    assert len(d.recommend) == 1
    assert d.priority_order == []


# --------------------------------------------------------------------------- #
# No "high-dose" recommendation is ever emitted (UL ceiling property)
# --------------------------------------------------------------------------- #
def test_no_high_dose_recommendation_anywhere(profiles):
    for pid, p in profiles.items():
        d = evaluate(p)
        for r in d.recommend:
            assert "high-dose" not in r.supplement.lower(), (
                f"{pid}: high-dose supplement must never be recommended, only blocked"
            )
