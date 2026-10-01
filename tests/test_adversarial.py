"""Adversarial-set tests.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

All 10 adversarial profiles must yield a ZERO engine unsafe-output rate, and the
extraction-targeting ones (misleading units) must be REJECTED (or safely
CONVERTED where the alternate unit is recognized) rather than guessed.
"""

from __future__ import annotations

import pytest

from supplement_engine.eval.cases import (
    adversarial_cases,
    questionnaire_from_record,
)
from supplement_engine.eval.harness import _score_case
from supplement_engine.extraction import ExtractionError, extract_profile

CASES = adversarial_cases()
CASE_IDS = [c.profile_id for c in CASES]


def test_ten_adversarial_profiles():
    assert len(CASES) == 10
    axes = {t for c in CASES for t in c.tags}
    for required in (
        "misleading_units",
        "overlooked_medication",
        "plausible_wrong_deficiency",
        "alarming_age_appropriate",
    ):
        assert required in axes


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_adversarial_engine_unsafe_rate_is_zero(case):
    row = _score_case(case)
    assert not row.unsafe, f"{case.profile_id} produced an unsafe output: {row.unsafe_reasons}"


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c.is_extraction_target],
    ids=[c.profile_id for c in CASES if c.is_extraction_target],
)
def test_extraction_targets_rejected_or_converted(case):
    q = questionnaire_from_record(case.record)
    if case.extraction_expectation == "reject":
        with pytest.raises(ExtractionError):
            extract_profile(case.bad_labs, q)
    elif case.extraction_expectation == "convert":
        result = extract_profile(case.bad_labs, q)
        assert result.conversions, f"{case.profile_id}: expected a recorded unit conversion"
    else:  # pragma: no cover - guard against new expectations
        pytest.fail(f"unknown extraction_expectation: {case.extraction_expectation}")


def test_at_least_one_hard_rejection():
    rejects = [c for c in CASES if c.extraction_expectation == "reject"]
    assert len(rejects) >= 2, "need genuine extraction rejections among the adversarial set"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_adversarial_extraction_scored_safe(case):
    """Extraction scoring treats a correct reject/convert as accurate."""
    row = _score_case(case)
    assert row.extraction_ok, f"{case.profile_id}: {row.extraction_detail}"


def test_generator_is_deterministic_and_artifact_in_sync():
    """The generator emits identical JSON every run and the committed artifact
    (data/adversarial_profiles.json) matches it."""
    import importlib.util
    import json
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "data" / "adversarial_profiles.py"
    spec = importlib.util.spec_from_file_location("adv_gen_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module._serialize() == module._serialize()  # deterministic
    artifact = repo_root / "data" / "adversarial_profiles.json"
    assert json.loads(artifact.read_text()) == json.loads(module._serialize())


def test_determinism():
    rows_a = [_score_case(c) for c in adversarial_cases()]
    rows_b = [_score_case(c) for c in adversarial_cases()]
    assert [r.unsafe for r in rows_a] == [r.unsafe for r in rows_b]
    assert [r.rule_correct for r in rows_a] == [r.rule_correct for r in rows_b]
