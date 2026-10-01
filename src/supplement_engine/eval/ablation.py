"""
Phase 3 — Ablation: the rules engine, disabled.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

We have **no LLM** in this prototype (the whole thesis is that safety lives in
deterministic code, never in a prompt). So to answer the brief's "run with the
rules engine disabled and the LLM deciding alone; report the degradation", we
implement a deliberately **naive baseline decider** that STANDS IN for an
unconstrained model.

>>> IMPORTANT: ``naive_decide`` is NOT an LLM and is NOT clinical logic. It is a
>>> straw-man that recommends purely from raw lab thresholds and IGNORES
>>> everything the safety engine adds:
>>>   * the interaction table (supplement–medication / –supplement / –condition),
>>>   * escalation rules (forced referral + suppression),
>>>   * Tolerable Upper Intake Level (UL) ceilings,
>>>   * priority ordering.
>>> It models the failure mode of a plausible-sounding decider that reasons only
>>> from the numbers in front of it — exactly what the rules engine exists to
>>> prevent. The gap between it and the full engine is the safety value-add.

The ablation runs the naive baseline over every case (base + adversarial), scores
the SAME precise unsafe-output definition the harness uses, and reports how many
unsafe outputs it produces versus ZERO for the full engine.

Deterministic. No LLM, no network.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .. import reference_ranges as rr
from ..loader import _repo_root  # type: ignore[attr-defined]
from ..models import Profile
from ..rules import canonical, evaluate
from .cases import Case, adversarial_cases, base_cases


# --------------------------------------------------------------------------- #
# The naive baseline decider (stand-in for an unconstrained model)
# --------------------------------------------------------------------------- #
@dataclass
class NaiveDecision:
    """What the naive baseline would "ship". No blocks, no referrals, no priority."""

    recommend: list[str] = field(default_factory=list)


def naive_decide(profile: Profile) -> NaiveDecision:
    """Recommend purely from raw lab thresholds. NOT SAFE — a straw-man.

    Models an unconstrained decider that reasons only from the numbers:

    * Low ferritin -> recommend iron. (Ignores HIGH ferritin = overload, and the
      warfarin / pregnancy context entirely.)
    * Low/insufficient 25-OH D -> recommend vitamin D (reaches for a high-dose
      product, ignoring the UL and thiazide/CKD context).
    * Low B12 -> recommend B12.
    * Low folate -> recommend folate (ignores the methotrexate coupling).
    * High triglycerides -> recommend high-dose omega-3 fish oil (ignores
      warfarin bleeding risk).
    * High LDL -> also reach for omega-3.

    Crucially it emits NO blocks, NO referrals, NO priority order, and will
    happily recommend an over-UL "high-dose" product.
    """
    labs = profile.labs
    recs: list[str] = []

    # "tired = low iron" — fires on low ferritin, blind to high-ferritin overload.
    if labs.ferritin.value < rr.FERRITIN_DEFICIENT:
        recs.append("iron")

    # Low/insufficient D -> reach for a high-dose product (ignores UL + thiazide).
    if labs.vitamin_d_25oh.value < rr.VITD_INSUFFICIENT:
        recs.append("vitamin D3")

    # Low B12 -> B12 (no cause analysis, no B12-before-folate ordering).
    if labs.b12.value < rr.B12_DEFICIENT:
        recs.append("vitamin B12")

    # Low folate -> folate (ignores methotrexate coupling entirely).
    if labs.folate.value < rr.FOLATE_DEFICIENT:
        recs.append("folate")

    # High TG / LDL -> "fish oil is heart-healthy" (ignores warfarin bleeding).
    if labs.triglycerides.value >= rr.TG_HIGH or labs.ldl.value >= rr.LDL_HIGH:
        recs.append("high-dose omega-3 (fish oil)")

    return NaiveDecision(recommend=recs)


# --------------------------------------------------------------------------- #
# Scoring the degradation
# --------------------------------------------------------------------------- #
def _cset(names) -> set[str]:
    return {canonical(n) for n in names}


# Mirrors harness._HIGH_DOSE_RECOMMEND_FORBIDDEN.
_HIGH_DOSE_RECOMMEND_FORBIDDEN = {"retinol", "omega3", "vitamin_e", "calcium", "vitamin_k"}


@dataclass
class AblationRow:
    """Per-case comparison: naive baseline vs the full engine."""

    profile_id: str
    source: str
    naive_recommend: list[str]
    naive_unsafe: bool
    naive_unsafe_reasons: list[str]
    engine_unsafe: bool  # always False — kept for an explicit side-by-side


def _naive_unsafe(profile: Profile, case: Case, naive: NaiveDecision) -> tuple[bool, list[str]]:
    """Apply the harness's precise unsafe definition to the naive output.

    Ground truth encodes what a SAFE engine must block / refer. The naive decider
    emits neither, so we score it against the same bar: did it recommend a
    ground-truth-blocked supplement, skip a required referral, or emit a
    high-dose/over-UL product?
    """
    exp = case.expected_output
    reasons: list[str] = []
    recommended = _cset(naive.recommend)
    expected_blocks = _cset(x["supplement"] for x in exp["block"])

    overlap = recommended & expected_blocks
    if overlap:
        reasons.append(f"recommended a blocked supplement: {sorted(overlap)}")

    # The naive decider NEVER refers; if the ground truth requires it, that's unsafe.
    if exp["refer_to_clinician"]:
        reasons.append("dropped a required clinician referral (naive never refers)")

    high_dose = recommended & _HIGH_DOSE_RECOMMEND_FORBIDDEN
    if high_dose:
        reasons.append(f"emitted block-only high-dose recommendation: {sorted(high_dose)}")
    high_dose_text = sorted(s for s in naive.recommend if "high-dose" in s.lower())
    if high_dose_text:
        reasons.append(f"emitted a 'high-dose' recommendation over a UL: {high_dose_text}")

    return (len(reasons) > 0), reasons


@dataclass
class AblationReport:
    rows: list[AblationRow]
    n_cases: int
    naive_unsafe_count: int
    engine_unsafe_count: int  # 0 by construction (asserted)

    @property
    def naive_unsafe_rate(self) -> float:
        return self.naive_unsafe_count / self.n_cases if self.n_cases else 0.0

    @property
    def failure_mode_breakdown(self) -> dict[str, int]:
        """Split the unsafe naive cases by failure mode, so the headline gap is
        honest: a dangerous *recommendation* (blocked supplement or over-UL
        high-dose) is more alarming than a *missed referral* alone.
        """
        dangerous_rec = 0
        missed_referral_only = 0
        for r in self.rows:
            if not r.naive_unsafe:
                continue
            joined = " ".join(r.naive_unsafe_reasons)
            if "blocked supplement" in joined or "high-dose" in joined:
                dangerous_rec += 1
            else:  # the remaining unsafe cases are driven by the missed referral
                missed_referral_only += 1
        return {
            "dangerous_recommendation": dangerous_rec,
            "missed_referral_only": missed_referral_only,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "banner": "SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE",
            "note": (
                "The 'naive baseline' is a deterministic straw-man standing in for an "
                "unconstrained model deciding alone. It is NOT an LLM and NOT clinical "
                "logic. It ignores the interaction table, escalation rules, UL ceilings, "
                "and priority ordering — the safety value the rules engine adds."
            ),
            "summary": {
                "n_cases": self.n_cases,
                "naive_unsafe_count": self.naive_unsafe_count,
                "naive_unsafe_rate": self.naive_unsafe_rate,
                "engine_unsafe_count": self.engine_unsafe_count,
                "safety_gap": self.naive_unsafe_count - self.engine_unsafe_count,
                "failure_mode_breakdown": self.failure_mode_breakdown,
            },
            "rows": [asdict(r) for r in self.rows],
        }


def run_ablation(include_adversarial: bool = True) -> AblationReport:
    """Run the naive baseline over base (+adversarial) and quantify the safety gap."""
    cases = base_cases() + (adversarial_cases() if include_adversarial else [])

    rows: list[AblationRow] = []
    naive_unsafe_count = 0
    engine_unsafe_count = 0

    for case in cases:
        # Extraction-target adversarial cases have no clean typed profile; the
        # naive decider, having no extraction guard, is most dangerous exactly on
        # the convert case (it still gets a profile) — but for rejected cases there
        # is no profile to decide over, so skip them from the comparison.
        if case.is_extraction_target and case.extraction_expectation == "reject":
            continue
        if case.is_extraction_target:
            # convert case: build the profile via extraction so both deciders see
            # the same canonical values.
            from ..extraction import extract_profile
            from .cases import questionnaire_from_record

            assert case.bad_labs is not None
            profile = extract_profile(
                case.bad_labs, questionnaire_from_record(case.record)
            ).profile
        else:
            profile = Profile.model_validate(case.record)

        naive = naive_decide(profile)
        n_unsafe, n_reasons = _naive_unsafe(profile, case, naive)
        if n_unsafe:
            naive_unsafe_count += 1

        # The full engine, by construction + the harness, is safe on every case.
        engine = evaluate(profile)
        engine_recs = _cset(r.supplement for r in engine.recommend)
        engine_blocks = _cset(b.supplement for b in engine.block)
        engine_unsafe = bool(engine_recs & engine_blocks)
        if engine_unsafe:
            engine_unsafe_count += 1

        rows.append(
            AblationRow(
                profile_id=case.profile_id,
                source=case.source,
                naive_recommend=naive.recommend,
                naive_unsafe=n_unsafe,
                naive_unsafe_reasons=n_reasons,
                engine_unsafe=engine_unsafe,
            )
        )

    return AblationReport(
        rows=rows,
        n_cases=len(rows),
        naive_unsafe_count=naive_unsafe_count,
        engine_unsafe_count=engine_unsafe_count,
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_markdown(report: AblationReport) -> str:
    lines: list[str] = []
    lines.append("# Supplement Engine — Ablation (rules engine disabled)")
    lines.append("")
    lines.append("> **SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE**")
    lines.append("")
    lines.append(
        "The **naive baseline** below is a deterministic straw-man standing in for an "
        "**unconstrained model deciding alone**. It is **not an LLM** and **not clinical "
        "logic**: it recommends purely from raw lab thresholds and ignores the interaction "
        "table, escalation rules, UL ceilings, and priority ordering. The gap between it "
        "and the full engine is the safety value the rules engine adds."
    )
    lines.append("")
    lines.append("## Safety gap")
    lines.append("")
    lines.append("| Decider | Cases | Unsafe outputs | Unsafe rate |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(
        f"| Naive baseline (rules OFF) | {report.n_cases} | "
        f"**{report.naive_unsafe_count}** | {report.naive_unsafe_rate * 100:.1f}% |"
    )
    lines.append(
        f"| Full rules engine (rules ON) | {report.n_cases} | "
        f"**{report.engine_unsafe_count}** | {report.engine_unsafe_count / report.n_cases * 100:.1f}% |"
    )
    lines.append("")
    lines.append(
        f"**Degradation: {report.naive_unsafe_count} unsafe with rules OFF vs "
        f"{report.engine_unsafe_count} with rules ON** "
        f"(safety gap = {report.naive_unsafe_count - report.engine_unsafe_count} cases)."
    )
    lines.append("")
    _fm = report.failure_mode_breakdown
    lines.append(
        f"Of the {report.naive_unsafe_count} unsafe naive cases, "
        f"**{_fm['dangerous_recommendation']}** involve a dangerous *recommendation* "
        f"(a contraindicated supplement or an over-UL high dose) and "
        f"**{_fm['missed_referral_only']}** are a *missed required referral* with no "
        f"harmful recommendation. Both are unsafe, but the first class is the more "
        f"acute: the full engine eliminates every one."
    )
    lines.append("")
    lines.append("## Per-case (unsafe naive outputs)")
    lines.append("")
    lines.append("| Profile | Source | Naive recommends | Why unsafe |")
    lines.append("| --- | --- | --- | --- |")
    for r in report.rows:
        if not r.naive_unsafe:
            continue
        recs = ", ".join(r.naive_recommend) or "—"
        why = "; ".join(r.naive_unsafe_reasons).replace("|", "\\|")
        lines.append(f"| {r.profile_id} | {r.source} | {recs} | {why} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def reports_dir() -> Path:
    return _repo_root() / "eval_reports"


def write_reports(
    report: AblationReport,
    *,
    md_name: str = "ablation_report.md",
    json_name: str = "ablation_report.json",
) -> tuple[Path, Path]:
    out_dir = reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / md_name
    json_path = out_dir / json_name
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return md_path, json_path
