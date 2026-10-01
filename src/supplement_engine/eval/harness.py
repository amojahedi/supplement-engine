"""
Phase 3 — Evaluation harness.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Scores every profile (base 30 + optional adversarial 10) on four axes and emits
a structured :class:`EvalReport` plus a markdown table and a JSON artifact.

Metrics
-------
* **Extraction accuracy** — round-trip each profile's labs through
  :func:`extraction.extract_profile` (rebuilding a raw-labs + questionnaire dict
  from the record) and confirm the canonical units and values are recovered.
  For adversarial cases that attack extraction, "accurate" means the extractor
  does the SAFE thing: REJECT a bad unit / implausible value, or CONVERT a
  recognized alternate unit.
* **Rule correctness** — :func:`rules.evaluate` output vs the hand-authored
  ``expected_output`` on STRUCTURED fields: recommend set, priority order, block
  set, refer flag, recommend_nothing flag, timing presence. Supplement names are
  canonicalized (reusing :func:`rules.canonical`). The documented P13 priority
  deviation is honored exactly as the ground-truth tests do.
* **Grounding pass rate** — fraction of rule-derived claims that pass the guard
  (claims_from_decision -> guard_claims over retrieved passages).
* **Unsafe-output rate** — MUST be zero. "Unsafe" is defined precisely below.

Unsafe-output definition
-------------------------
A case is UNSAFE iff ANY of:
  1. it recommends a supplement the ground truth blocks (or whose canonical
     identity is blocked);  OR
  2. it drops a referral the ground truth requires (refer expected, not emitted);
     OR
  3. it emits a "high-dose" recommendation (a rec whose text/identity names a
     high-dose/over-UL supplement — such a thing may only ever be a BLOCK).

Deterministic throughout. No LLM, no network.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..extraction import ExtractionError, extract_profile
from ..loader import _repo_root  # type: ignore[attr-defined]
from ..models import Profile
from ..pipeline import run_case
from ..rules import canonical, evaluate
from .cases import (
    Case,
    adversarial_cases,
    base_cases,
    questionnaire_from_record,
    raw_labs_from_record,
)

# Mirrors tests/test_ground_truth.py: P13's authored priority lists folate before
# B12, but the brief makes "B12 before folate" a safety property, so the engine
# emits B12 first. We assert the safety property for P13 rather than the exact
# authored sequence.
PRIORITY_SEQUENCE_EXACT_EXCEPTIONS = {"P13"}

# Canonical identities that denote a "high-dose"/over-UL-only product. In this
# engine these supplements exist ONLY as contraindication BLOCKS (teratogenic
# retinol, warfarin-interacting omega-3 / vitamin E / vitamin K, thiazide-
# interacting high-dose calcium). If one ever shows up as a RECOMMEND it means a
# hard ceiling / UL was breached — which is unsafe by definition. Standard-dose
# repletion supplements (iron, vitamin D, folate, B12) are NOT in this set: they
# have ULs but a normal rec sits far below the ceiling and is safe.
_HIGH_DOSE_RECOMMEND_FORBIDDEN = {"retinol", "omega3", "vitamin_e", "calcium", "vitamin_k"}


def _cset(names) -> set[str]:
    return {canonical(n) for n in names}


def _clist(names) -> list[str]:
    return [canonical(n) for n in names]


# --------------------------------------------------------------------------- #
# Result rows
# --------------------------------------------------------------------------- #
@dataclass
class CaseRow:
    """Per-case scoring row."""

    profile_id: str
    source: str
    tags: list[str]

    extraction_ok: bool
    extraction_detail: str

    rule_correct: bool
    rule_detail: str

    grounding_total: int
    grounding_passed: int

    unsafe: bool
    unsafe_reasons: list[str] = field(default_factory=list)

    @property
    def grounding_rate(self) -> float:
        return (self.grounding_passed / self.grounding_total) if self.grounding_total else 1.0


@dataclass
class Aggregate:
    """Aggregate metrics over a set of rows."""

    n_cases: int
    extraction_accuracy: float
    rule_correctness: float
    rule_correct_count: int
    grounding_pass_rate: float
    unsafe_count: int
    unsafe_rate: float


@dataclass
class EvalReport:
    """Structured eval report: per-case rows + aggregates (base / adversarial / all)."""

    rows: list[CaseRow]
    base: Aggregate
    adversarial: Aggregate | None
    overall: Aggregate

    def to_dict(self) -> dict[str, Any]:
        return {
            "banner": "SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE",
            "rows": [asdict(r) for r in self.rows],
            "aggregates": {
                "base": asdict(self.base),
                "adversarial": asdict(self.adversarial) if self.adversarial else None,
                "overall": asdict(self.overall),
            },
        }


# --------------------------------------------------------------------------- #
# Scoring one case
# --------------------------------------------------------------------------- #
def _score_extraction(case: Case) -> tuple[bool, str, Profile | None]:
    """Round-trip extraction. Returns (ok, detail, profile_or_None).

    For a normal case: extraction must succeed AND recover canonical units and the
    original numeric values. For an adversarial extraction-target: the SAFE
    behavior (reject / convert) is what counts as accurate.
    """
    rec = case.record
    q = questionnaire_from_record(rec)

    if case.is_extraction_target:
        assert case.bad_labs is not None
        try:
            result = extract_profile(case.bad_labs, q)
        except ExtractionError as exc:
            if case.extraction_expectation == "reject":
                return True, f"correctly REJECTED: {exc}", None
            return False, f"unexpected rejection (expected {case.extraction_expectation}): {exc}", None
        # Extraction succeeded.
        if case.extraction_expectation == "reject":
            return False, "UNSAFE: bad-unit input was accepted instead of rejected", result.profile
        if case.extraction_expectation == "convert":
            if not result.conversions:
                return False, "expected a unit conversion but none was recorded", result.profile
            detail = "; ".join(
                f"{c.analyte} {c.original_value}{c.from_unit}->{c.converted_value:.2f}{c.to_unit}"
                for c in result.conversions
            )
            return True, f"correctly CONVERTED: {detail}", result.profile
        return True, "extracted", result.profile

    # Normal case: identity round-trip must recover canonical units + values.
    raw_labs = raw_labs_from_record(rec)
    try:
        result = extract_profile(raw_labs, q)
    except ExtractionError as exc:
        return False, f"extraction failed on a valid profile: {exc}", None

    profile = result.profile
    # Confirm each simple analyte value survived the round-trip.
    expected_vals = {
        "ferritin": profile.labs.ferritin,
        "vitamin_d_25oh": profile.labs.vitamin_d_25oh,
        "b12": profile.labs.b12,
        "folate": profile.labs.folate,
        "tsh": profile.labs.tsh,
        "hba1c": profile.labs.hba1c,
    }
    for analyte, lv in expected_vals.items():
        raw = raw_labs[analyte]
        if abs(lv.value - float(raw["value"])) > 1e-9:
            return False, f"{analyte} value drifted on round-trip", profile
        if lv.unit != raw["unit"]:
            return False, f"{analyte} unit not canonical after round-trip", profile
    return True, "round-trip recovered canonical units + values", profile


def _score_rule_correctness(profile: Profile, case: Case) -> tuple[bool, str]:
    """Compare engine decision vs ground truth on structured fields."""
    d = evaluate(profile)
    exp = case.expected_output

    checks: list[str] = []
    ok = True

    if _cset(r.supplement for r in d.recommend) != _cset(x["supplement"] for x in exp["recommend"]):
        ok = False
        checks.append("recommend-set")
    if _cset(b.supplement for b in d.block) != _cset(x["supplement"] for x in exp["block"]):
        ok = False
        checks.append("block-set")
    if d.refer_to_clinician != exp["refer_to_clinician"]:
        ok = False
        checks.append("refer-flag")
    if d.recommend_nothing != exp["recommend_nothing"]:
        ok = False
        checks.append("recommend_nothing-flag")
    if bool(d.timing_cautions) != bool(exp["timing_cautions"]):
        ok = False
        checks.append("timing-presence")

    got = _clist(d.priority_order)
    want = _clist(exp["priority_order"])
    if set(got) != set(want):
        ok = False
        checks.append("priority-set")
    elif case.profile_id in PRIORITY_SEQUENCE_EXACT_EXCEPTIONS:
        if "vitamin_b12" in got and "folate" in got and got.index("vitamin_b12") >= got.index("folate"):
            ok = False
            checks.append("priority-safety(B12<folate)")
    elif got != want:
        ok = False
        checks.append("priority-order")

    return ok, ("all structured fields match" if ok else "mismatch: " + ", ".join(checks))


def _score_grounding(profile: Profile) -> tuple[int, int]:
    """Run retrieval + grounding guard; return (total_claims, passed_claims)."""
    decision = evaluate(profile)
    result = run_case(profile, decision)
    total = len(result.guarded.kept_claims) + len(result.guarded.dropped_claims)
    passed = len(result.guarded.kept_claims)
    return total, passed


def _score_unsafe(profile: Profile, case: Case) -> tuple[bool, list[str]]:
    """Apply the precise unsafe-output definition. Returns (unsafe, reasons)."""
    d = evaluate(profile)
    exp = case.expected_output
    reasons: list[str] = []

    expected_blocks = _cset(x["supplement"] for x in exp["block"])
    recommended = _cset(r.supplement for r in d.recommend)

    # 1. Recommended a supplement the ground truth blocks.
    overlap = recommended & expected_blocks
    if overlap:
        reasons.append(f"recommended a blocked supplement: {sorted(overlap)}")

    # Also catch recommending anything the engine itself blocked (self-contradiction).
    engine_blocks = _cset(b.supplement for b in d.block)
    self_overlap = recommended & engine_blocks
    if self_overlap:
        reasons.append(f"recommended an engine-blocked supplement: {sorted(self_overlap)}")

    # 2. Dropped a required referral.
    if exp["refer_to_clinician"] and not d.refer_to_clinician:
        reasons.append("dropped a required clinician referral")

    # Also: failed to surface a block the ground truth requires.
    missing_blocks = expected_blocks - engine_blocks
    if missing_blocks:
        reasons.append(f"failed to block required supplement(s): {sorted(missing_blocks)}")

    # 3. Emitted a high-dose / over-UL recommendation (may only ever be a BLOCK).
    #    Two signals: a canonical identity that is block-only, OR a display name
    #    that literally advertises a "high-dose" product.
    high_dose_recs = recommended & _HIGH_DOSE_RECOMMEND_FORBIDDEN
    if high_dose_recs:
        reasons.append(f"emitted block-only high-dose recommendation: {sorted(high_dose_recs)}")
    high_dose_text = sorted(
        r.supplement for r in d.recommend if "high-dose" in r.supplement.lower()
    )
    if high_dose_text:
        reasons.append(f"emitted a 'high-dose' recommendation over a UL: {high_dose_text}")

    return (len(reasons) > 0), reasons


def _score_case(case: Case) -> CaseRow:
    extraction_ok, extraction_detail, profile = _score_extraction(case)

    if case.is_extraction_target:
        # Extraction-target cases: the ONLY thing that matters is safe extraction.
        # A rejected case has no decision to evaluate; a converted case is scored
        # as a normal case below using its converted profile.
        if profile is None:
            return CaseRow(
                profile_id=case.profile_id,
                source=case.source,
                tags=case.tags,
                extraction_ok=extraction_ok,
                extraction_detail=extraction_detail,
                rule_correct=extraction_ok,  # safe rejection == correct behavior
                rule_detail="rejected at extraction (no decision to evaluate)",
                grounding_total=0,
                grounding_passed=0,
                unsafe=not extraction_ok,
                unsafe_reasons=([] if extraction_ok else ["accepted an unsafe-unit input"]),
            )
        # Converted: fall through to normal scoring on the converted profile.

    assert profile is not None
    rule_correct, rule_detail = _score_rule_correctness(profile, case)
    g_total, g_passed = _score_grounding(profile)
    unsafe, unsafe_reasons = _score_unsafe(profile, case)

    return CaseRow(
        profile_id=case.profile_id,
        source=case.source,
        tags=case.tags,
        extraction_ok=extraction_ok,
        extraction_detail=extraction_detail,
        rule_correct=rule_correct,
        rule_detail=rule_detail,
        grounding_total=g_total,
        grounding_passed=g_passed,
        unsafe=unsafe,
        unsafe_reasons=unsafe_reasons,
    )


# --------------------------------------------------------------------------- #
# Aggregation + top-level run
# --------------------------------------------------------------------------- #
def _aggregate(rows: list[CaseRow]) -> Aggregate:
    n = len(rows)
    if n == 0:
        return Aggregate(0, 1.0, 1.0, 0, 1.0, 0, 0.0)
    extraction_acc = sum(r.extraction_ok for r in rows) / n
    rule_count = sum(r.rule_correct for r in rows)
    rule_corr = rule_count / n
    g_total = sum(r.grounding_total for r in rows)
    g_passed = sum(r.grounding_passed for r in rows)
    grounding_rate = (g_passed / g_total) if g_total else 1.0
    unsafe_count = sum(r.unsafe for r in rows)
    return Aggregate(
        n_cases=n,
        extraction_accuracy=extraction_acc,
        rule_correctness=rule_corr,
        rule_correct_count=rule_count,
        grounding_pass_rate=grounding_rate,
        unsafe_count=unsafe_count,
        unsafe_rate=unsafe_count / n,
    )


def run_eval(include_adversarial: bool = True) -> EvalReport:
    """Score the base set (and optionally the adversarial set) and return a report."""
    base = base_cases()
    rows = [_score_case(c) for c in base]
    base_rows = rows

    adv_rows: list[CaseRow] = []
    if include_adversarial:
        adv = adversarial_cases()
        adv_rows = [_score_case(c) for c in adv]
        rows = rows + adv_rows

    return EvalReport(
        rows=rows,
        base=_aggregate(base_rows),
        adversarial=_aggregate(adv_rows) if include_adversarial else None,
        overall=_aggregate(rows),
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_markdown(report: EvalReport) -> str:
    lines: list[str] = []
    lines.append("# Supplement Engine — Evaluation Report")
    lines.append("")
    lines.append("> **SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE**")
    lines.append("")
    lines.append("Deterministic rules engine. No LLM anywhere in the safety path.")
    lines.append("")

    lines.append("## Aggregates")
    lines.append("")
    lines.append("| Set | Cases | Extraction acc. | Rule correctness | Grounding pass | Unsafe-output rate |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")

    def agg_row(name: str, a: Aggregate) -> str:
        return (
            f"| {name} | {a.n_cases} | {_pct(a.extraction_accuracy)} | "
            f"{_pct(a.rule_correctness)} ({a.rule_correct_count}/{a.n_cases}) | "
            f"{_pct(a.grounding_pass_rate)} | **{_pct(a.unsafe_rate)}** ({a.unsafe_count}) |"
        )

    lines.append(agg_row("Base (30)", report.base))
    if report.adversarial:
        lines.append(agg_row("Adversarial (10)", report.adversarial))
    lines.append(agg_row("Overall", report.overall))
    lines.append("")

    lines.append("## Per-case")
    lines.append("")
    lines.append("| Profile | Source | Extraction | Rule-correct | Grounding | Unsafe | Notes |")
    lines.append("| --- | --- | :---: | :---: | ---: | :---: | --- |")
    for r in report.rows:
        extraction_mark = "✓" if r.extraction_ok else "✗"
        rule_mark = "✓" if r.rule_correct else "✗"
        unsafe_mark = "UNSAFE" if r.unsafe else "safe"
        grounding = f"{r.grounding_passed}/{r.grounding_total}" if r.grounding_total else "—"
        note = r.rule_detail if not r.rule_correct else r.extraction_detail
        note = note.replace("|", "\\|")
        lines.append(
            f"| {r.profile_id} | {r.source} | {extraction_mark} | {rule_mark} | "
            f"{grounding} | {unsafe_mark} | {note} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def reports_dir() -> Path:
    return _repo_root() / "eval_reports"


def write_reports(
    report: EvalReport,
    *,
    md_name: str = "base_report.md",
    json_name: str = "base_report.json",
) -> tuple[Path, Path]:
    """Write the markdown table and JSON artifact; return the two paths."""
    out_dir = reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / md_name
    json_path = out_dir / json_name
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return md_path, json_path
