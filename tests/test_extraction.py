"""Tests for Stage 1 extraction — the reject-rather-than-guess unit posture.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

import pytest

from supplement_engine.extraction import (
    ExtractionError,
    assert_expected_units,
    extract_profile,
)


def _labs(**overrides):
    """A valid canonical-unit lab dict; override individual analytes per test."""
    labs = {
        "ferritin": {"value": 12, "unit": "ng/mL"},
        "vitamin_d_25oh": {"value": 18, "unit": "ng/mL"},
        "b12": {"value": 210, "unit": "pg/mL"},
        "folate": {"value": 6, "unit": "ng/mL"},
        "tsh": {"value": 2.1, "unit": "mIU/L"},
        "hba1c": {"value": 5.3, "unit": "%"},
        "lipids": {
            "total_chol": {"value": 180, "unit": "mg/dL"},
            "ldl": {"value": 100, "unit": "mg/dL"},
            "hdl": {"value": 55, "unit": "mg/dL"},
            "triglycerides": {"value": 120, "unit": "mg/dL"},
        },
    }
    labs.update(overrides)
    return labs


def _questionnaire(**overrides):
    q = {
        "profile_id": "TEST",
        "age": 34,
        "sex": "female",
        "pregnant": False,
        "diet": "omnivore",
        "sun_exposure": "moderate",
        "gi_conditions": [],
        "pregnancy_status": "not_pregnant",
        "notes": "",
        "medications": [],
    }
    q.update(overrides)
    return q


def test_valid_parse_produces_canonical_profile():
    result = extract_profile(_labs(), _questionnaire())
    assert result.profile.profile_id == "TEST"
    assert result.profile.labs.ferritin.value == 12
    assert result.profile.labs.ferritin.unit == "ng/mL"
    assert result.conversions == []
    # The guard passes on the produced profile.
    assert_expected_units(result.profile.labs)


def test_missing_unit_is_rejected_not_defaulted():
    with pytest.raises(ExtractionError, match="missing unit"):
        extract_profile(_labs(vitamin_d_25oh={"value": 18}), _questionnaire())


def test_unknown_unit_is_rejected():
    with pytest.raises(ExtractionError, match="unrecognized unit"):
        extract_profile(_labs(b12={"value": 210, "unit": "pg/dL"}), _questionnaire())


def test_empty_unit_is_rejected():
    with pytest.raises(ExtractionError, match="missing unit"):
        extract_profile(_labs(ferritin={"value": 12, "unit": ""}), _questionnaire())


def test_implausible_value_flags_mislabeled_unit():
    # 18 labeled ng/mL is fine; 18000 ng/mL vitamin D is physically impossible.
    with pytest.raises(ExtractionError, match="outside the plausible range"):
        extract_profile(
            _labs(vitamin_d_25oh={"value": 18000, "unit": "ng/mL"}), _questionnaire()
        )


def test_nonnumeric_value_is_rejected():
    with pytest.raises(ExtractionError, match="not numeric"):
        extract_profile(_labs(tsh={"value": "high", "unit": "mIU/L"}), _questionnaire())


def test_vitamin_d_nmol_conversion_correctness():
    # 75 nmol/L / 2.496 ~= 30.05 ng/mL.
    result = extract_profile(
        _labs(vitamin_d_25oh={"value": 75, "unit": "nmol/L"}), _questionnaire()
    )
    assert result.profile.labs.vitamin_d_25oh.unit == "ng/mL"
    assert result.profile.labs.vitamin_d_25oh.value == pytest.approx(75 / 2.496, rel=1e-6)
    assert len(result.conversions) == 1
    conv = result.conversions[0]
    assert conv.analyte == "vitamin_d_25oh"
    assert conv.from_unit == "nmol/L"
    assert conv.to_unit == "ng/mL"


def test_b12_pmol_conversion_correctness():
    # 148 pmol/L / 0.7378 ~= 200.6 pg/mL.
    result = extract_profile(_labs(b12={"value": 148, "unit": "pmol/L"}), _questionnaire())
    assert result.profile.labs.b12.unit == "pg/mL"
    assert result.profile.labs.b12.value == pytest.approx(148 / 0.7378, rel=1e-6)


def test_missing_profile_id_rejected():
    q = _questionnaire()
    del q["profile_id"]
    with pytest.raises(ExtractionError, match="missing profile_id"):
        extract_profile(_labs(), q)


def test_missing_lab_rejected():
    labs = _labs()
    del labs["folate"]
    with pytest.raises(ExtractionError, match="missing lab: folate"):
        extract_profile(labs, _questionnaire())


def test_assert_expected_units_catches_noncanonical():
    # Build a valid profile then corrupt a unit to prove the guard fires.
    result = extract_profile(_labs(), _questionnaire())
    result.profile.labs.ferritin.unit = "nmol/L"
    with pytest.raises(ExtractionError, match="expected canonical"):
        assert_expected_units(result.profile.labs)


def test_extracted_profile_feeds_rules_engine():
    from supplement_engine.rules import evaluate

    result = extract_profile(_labs(), _questionnaire())
    decision = evaluate(result.profile)
    # ferritin 12 -> iron deficiency should be recommended.
    assert "iron" in [r.supplement.lower() for r in decision.recommend]
