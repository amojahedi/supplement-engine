"""Ablation tests.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

The rules-disabled naive baseline (a stand-in for an unconstrained model) must
demonstrably produce > 0 unsafe outputs — proving the rules engine matters —
while the full engine produces zero. The report must quantify that gap, and the
whole thing must be deterministic.
"""

from __future__ import annotations

from supplement_engine.eval.ablation import (
    naive_decide,
    render_markdown,
    run_ablation,
    write_reports,
)
from supplement_engine.loader import load_profile


def test_naive_baseline_is_unsafe_and_engine_is_not():
    report = run_ablation(include_adversarial=True)
    assert report.naive_unsafe_count > 0, "ablation must show the naive baseline is unsafe"
    assert report.engine_unsafe_count == 0, "the full engine must be safe on every case"
    assert report.naive_unsafe_count > report.engine_unsafe_count


def test_report_quantifies_the_gap():
    report = run_ablation(include_adversarial=True)
    summary = report.to_dict()["summary"]
    assert summary["safety_gap"] == report.naive_unsafe_count - report.engine_unsafe_count
    assert summary["safety_gap"] > 0
    assert summary["naive_unsafe_count"] == report.naive_unsafe_count


def test_naive_recommends_blocked_supplement_somewhere():
    """At least one case: the naive baseline actively recommends a supplement the
    ground truth blocks (not merely a missed referral)."""
    report = run_ablation(include_adversarial=True)
    active_block_violations = [
        r for r in report.rows
        if any("recommended a blocked supplement" in reason for reason in r.naive_unsafe_reasons)
    ]
    assert active_block_violations, "expected the naive baseline to recommend a blocked supplement"


def test_naive_recommends_iron_on_high_ferritin():
    """P23 has HIGH ferritin; the engine blocks iron, but a raw-threshold decider
    does NOT recommend iron (ferritin is not < 30) — it simply misses the needed
    referral. The warfarin/omega case (P02) is where the active block violation
    shows up. This documents the naive decider's blindness."""
    p23 = load_profile("P23")
    naive = naive_decide(p23)
    assert "iron" not in naive.recommend  # high ferritin -> no low-ferritin trigger
    p02 = load_profile("P02")
    naive02 = naive_decide(p02)
    assert any("omega" in s.lower() for s in naive02.recommend)  # recommends blocked fish oil


def test_ablation_is_deterministic():
    r1 = run_ablation(include_adversarial=True)
    r2 = run_ablation(include_adversarial=True)
    assert r1.to_dict() == r2.to_dict()
    assert render_markdown(r1) == render_markdown(r2)


def test_write_reports(tmp_path, monkeypatch):
    from supplement_engine.eval import ablation

    monkeypatch.setattr(ablation, "reports_dir", lambda: tmp_path)
    report = run_ablation(include_adversarial=True)
    md_path, json_path = write_reports(report)
    assert md_path.exists() and json_path.exists()
    assert "Ablation" in md_path.read_text()
    assert "not an LLM" in md_path.read_text()
