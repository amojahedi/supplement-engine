"""Eval harness tests.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

The harness must report 30/30 rule-correct and a ZERO unsafe-output rate on the
base set, with 100% extraction accuracy and grounding pass rate, and must be
fully deterministic.
"""

from __future__ import annotations

from supplement_engine.eval.harness import (
    render_markdown,
    run_eval,
    write_reports,
)


def test_base_set_rule_correct_30_of_30():
    report = run_eval(include_adversarial=False)
    assert report.base.n_cases == 30
    assert report.base.rule_correct_count == 30
    assert report.base.rule_correctness == 1.0


def test_base_set_unsafe_rate_is_zero():
    report = run_eval(include_adversarial=False)
    assert report.base.unsafe_count == 0
    assert report.base.unsafe_rate == 0.0
    # And no individual row is flagged unsafe.
    assert all(not r.unsafe for r in report.rows)


def test_base_set_extraction_and_grounding():
    report = run_eval(include_adversarial=False)
    # Every base profile round-trips through extraction with canonical units.
    assert report.base.extraction_accuracy == 1.0
    # Every rule-derived claim passes the guard.
    assert report.base.grounding_pass_rate == 1.0


def test_overall_unsafe_rate_is_zero_with_adversarial():
    report = run_eval(include_adversarial=True)
    assert report.overall.n_cases == 40
    assert report.overall.unsafe_count == 0
    assert report.adversarial is not None
    assert report.adversarial.n_cases == 10


def test_report_is_deterministic():
    r1 = run_eval(include_adversarial=True)
    r2 = run_eval(include_adversarial=True)
    assert r1.to_dict() == r2.to_dict()
    assert render_markdown(r1) == render_markdown(r2)


def test_write_reports(tmp_path, monkeypatch):
    from supplement_engine.eval import harness

    monkeypatch.setattr(harness, "reports_dir", lambda: tmp_path)
    report = run_eval(include_adversarial=True)
    md_path, json_path = write_reports(report)
    assert md_path.exists() and json_path.exists()
    text = md_path.read_text()
    assert "Evaluation Report" in text
    assert "Unsafe-output rate" in text


def test_grounding_pass_rate_full():
    report = run_eval(include_adversarial=True)
    # No case drops a rule-derived claim (every hit traces to itself).
    for r in report.rows:
        assert r.grounding_passed == r.grounding_total
