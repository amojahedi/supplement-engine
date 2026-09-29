"""
The rules engine: a pure, deterministic function ``evaluate(profile)``.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

ZERO LLM involvement. Every decision — deficiency interpretation, escalation,
contraindication block, timing caution, priority ordering — is made here in
tested Python. The rationale text is generated deterministically from the fired
rule hits via template strings.

Decision pipeline (order matters and is a safety property):

1.  Interpret labs against age/sex/pregnancy-aware thresholds -> candidate
    deficiencies.
2.  Collect contraindication BLOCKS from the interaction table (medications,
    conditions, note-driven "asks about" exposures). Blocks always survive.
3.  Evaluate ESCALATIONS. An escalation forces ``refer_to_clinician=True`` and,
    for the suppressing kind, sets ``recommend_nothing=True`` and drops every
    recommendation — but relevant BLOCKS are still surfaced.
4.  Drop any candidate recommendation that a block contraindicates.
5.  Emit timing cautions.
6.  Order the surviving recommendations by the priority policy
    (iron-when-symptomatic, B12-before-folate, pregnancy-folate-first).
7.  Render the rationale from the fired rule hits.
"""

from __future__ import annotations

from . import reference_ranges as rr
from .interactions import (
    ACE_CKD_POTASSIUM,
    B12_BEFORE_FOLATE,
    CKD_MAGNESIUM,
    DIGOXIN_SJW,
    HIGH_FERRITIN_IRON,
    LEVO_IRON_TIMING,
    METFORMIN_B12,
    METHOTREXATE_FOLATE,
    PREGNANCY_RETINOL,
    SSRI_SJW,
    STATIN_SJW,
    THIAZIDE_CALCIUM,
    WARFARIN_OMEGA3,
    WARFARIN_VITE,
    WARFARIN_VITK,
    normalize_med,
)
from .models import (
    Action,
    Block,
    EngineDecision,
    Profile,
    Recommendation,
    RuleHit,
    TimingCaution,
)

# --------------------------------------------------------------------------- #
# Canonicalization
# --------------------------------------------------------------------------- #
# Downstream matching is done on canonical supplement identities so that
# "vitamin D3", "vitamin D3 (standard dose)", "vitamin D" all collapse to one.
_CANON = {
    "iron": "iron",
    "prenatal iron": "iron",
    "vitamin d": "vitamin_d",
    "vitamin d3": "vitamin_d",
    "vitamin d3 (standard dose)": "vitamin_d",
    "vitamin b12": "vitamin_b12",
    "b12": "vitamin_b12",
    "folate": "folate",
    "folic acid": "folate",
    "folate (folic acid)": "folate",
    "self-directed folate/folic acid": "folate",
    "st john's wort": "st_johns_wort",
    "high-dose vitamin a (retinol)": "retinol",
    "high-dose omega-3 (fish oil)": "omega3",
    "vitamin k supplement": "vitamin_k",
    "high-dose vitamin e": "vitamin_e",
    "high-dose calcium": "calcium",
    "potassium": "potassium",
    "magnesium": "magnesium",
}


def canonical(name: str) -> str:
    """Map a display supplement name to its canonical identity (robust matching)."""
    return _CANON.get(name.strip().lower(), name.strip().lower())


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _has(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def _is_pregnant(p: Profile) -> bool:
    return p.demographics.pregnant or p.intake.pregnancy_status.startswith("pregnant")


def _is_planning(p: Profile) -> bool:
    return p.intake.pregnancy_status in ("planning_pregnancy",)


def _has_ckd(p: Profile) -> bool:
    return _has(p.intake.notes, "kidney disease", "ckd") or "ckd" in [
        c.lower() for c in p.intake.gi_conditions
    ]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def evaluate(profile: Profile) -> EngineDecision:
    labs = profile.labs
    demo = profile.demographics
    notes = profile.intake.notes
    meds = {normalize_med(m) for m in profile.medications}
    diet = profile.intake.diet.lower()
    pregnant = _is_pregnant(profile)
    planning = _is_planning(profile)

    hits: list[RuleHit] = []
    recs: list[Recommendation] = []
    blocks: list[Block] = []
    timings: list[TimingCaution] = []
    refer = False
    recommend_nothing = False

    def add_rec(supp: str, reason: str, rule_id: str) -> None:
        recs.append(Recommendation(supplement=supp, reason=reason, rule_id=rule_id))
        hits.append(RuleHit(rule_id=rule_id, action=Action.RECOMMEND, subject=supp, reason=reason))

    def add_block(ix) -> None:
        # Idempotent per canonical subject: don't double-block the same thing.
        if any(canonical(b.supplement) == canonical(ix.subject) for b in blocks):
            return
        blocks.append(Block(supplement=ix.subject, reason=ix.reason, rule_id=ix.rule_id))
        hits.append(RuleHit(rule_id=ix.rule_id, action=Action.BLOCK,
                            subject=ix.subject, reason=ix.reason))

    def add_timing(ix) -> None:
        timings.append(TimingCaution(supplement=ix.subject, caution=ix.reason, rule_id=ix.rule_id))
        hits.append(RuleHit(rule_id=ix.rule_id, action=Action.TIMING_CAUTION,
                            subject=ix.subject, reason=ix.reason))

    # ----------------------------------------------------------------- #
    # STEP 1 — Contraindication BLOCKS (evaluated first: they win over recs)
    # ----------------------------------------------------------------- #
    # supplement–medication blocks
    if "warfarin" in meds:
        # Fish-oil block is surfaced when the patient is asking about it or has
        # high triglycerides (the otherwise-obvious rec).
        if _has(notes, "fish oil", "omega") or labs.triglycerides_high():
            add_block(WARFARIN_OMEGA3)
            refer = True
        if _has(notes, "vitamin k"):
            add_block(WARFARIN_VITK)
        if _has(notes, "vitamin e"):
            add_block(WARFARIN_VITE)

    if "ssri" in meds and _has(notes, "st john"):
        add_block(SSRI_SJW)
        refer = True
    if "statin" in meds and _has(notes, "st john"):
        add_block(STATIN_SJW)
        refer = True
    if "digoxin" in meds and _has(notes, "st john"):
        add_block(DIGOXIN_SJW)  # DIGOXIN_SJW.refer is False

    if "thiazide" in meds and _has(notes, "calcium"):
        add_block(THIAZIDE_CALCIUM)

    # supplement–condition blocks
    # Pregnancy hard-blocks high-dose retinol preventively (teratogen), whether or
    # not the patient has mentioned it — it is a standing contraindication.
    if pregnant:
        add_block(PREGNANCY_RETINOL)
        refer = True

    ckd = _has_ckd(profile)
    if ckd and "ace_inhibitor" in meds and _has(notes, "potassium"):
        add_block(ACE_CKD_POTASSIUM)
        refer = True
    if ckd and _has(notes, "magnesium"):
        add_block(CKD_MAGNESIUM)
        refer = True

    ferritin_high = labs.ferritin.value >= rr.ferritin_overload_ceiling(demo.sex)
    if ferritin_high:
        add_block(HIGH_FERRITIN_IRON)
        refer = True

    # ----------------------------------------------------------------- #
    # STEP 2 — ESCALATIONS (force referral; the suppressing kind drops all recs)
    # ----------------------------------------------------------------- #
    escalation_reasons: list[str] = []

    # Undiagnosed diabetes: very high HbA1c + classic symptoms, with no *managed*
    # diagnosis already in place. "No diabetes diagnosis" in the notes must NOT be
    # read as an existing diagnosis.
    diabetes_symptoms = _has(notes, "thirst", "weight loss", "blurry", "blurred")
    managed_diabetes = _has(notes, "type 2 diabetes", "well-controlled", "managed diabetes")
    if labs.hba1c.value >= rr.HBA1C_ESCALATION and diabetes_symptoms and not managed_diabetes:
        rid = "ESC-DIABETES"
        escalation_reasons.append(
            f"HbA1c {labs.hba1c.value}% with classic symptoms indicates likely undiagnosed "
            f"diabetes — a medical diagnosis, not a supplement problem."
        )
        hits.append(RuleHit(rule_id=rid, action=Action.ESCALATE, subject="undiagnosed diabetes",
                            reason=escalation_reasons[-1]))
        recommend_nothing = True
        refer = True

    # Thyroid: high TSH + symptoms, no existing diagnosis.
    thyroid_symptoms = _has(notes, "cold intoleran", "fatigue")
    if (labs.tsh.value > rr.TSH_HIGH and thyroid_symptoms
            and "no thyroid diagnosis" in notes.lower()):
        rid = "ESC-THYROID"
        escalation_reasons.append(
            f"TSH {labs.tsh.value} mIU/L with symptoms suggests subclinical/overt "
            f"hypothyroidism — a diagnostic and prescribing question."
        )
        hits.append(RuleHit(rule_id=rid, action=Action.ESCALATE, subject="thyroid",
                            reason=escalation_reasons[-1]))
        recommend_nothing = True
        refer = True

    # Severe multi-deficiency + unexplained weight loss -> systemic workup.
    severe_defs = sum([
        labs.ferritin.value < 10,
        labs.vitamin_d_25oh.value < rr.VITD_DEFICIENT,
        labs.b12.value < rr.B12_DEFICIENT,
        labs.folate.value < rr.FOLATE_DEFICIENT,
    ])
    weight_loss_signal = _has(notes, "unexplained weight loss") or (
        "unexplained_weight_loss" in [c.lower() for c in profile.intake.gi_conditions]
    )
    if severe_defs >= 3 and weight_loss_signal:
        rid = "ESC-MULTIDEF-WEIGHTLOSS"
        escalation_reasons.append(
            "Severe multi-nutrient deficiency with unexplained weight loss points to a "
            "systemic underlying cause; piecemeal supplementation would mask a serious workup."
        )
        hits.append(RuleHit(rule_id=rid, action=Action.ESCALATE,
                            subject="systemic workup", reason=escalation_reasons[-1]))
        recommend_nothing = True
        refer = True

    # Methotrexate + low folate: the folate regimen belongs to the prescriber.
    if "methotrexate" in meds and labs.folate.value < rr.FOLATE_DEFICIENT:
        add_block(METHOTREXATE_FOLATE)
        escalation_reasons.append(
            "With methotrexate the folate regimen is part of the drug therapy and must be set "
            "by the prescriber; defer entirely to the clinician."
        )
        hits.append(RuleHit(rule_id="ESC-MTX-FOLATE", action=Action.ESCALATE,
                            subject="methotrexate folate coupling", reason=escalation_reasons[-1]))
        recommend_nothing = True
        refer = True

    # CKD + ACE inhibitor electrolytes: defer entirely.
    if ckd and "ace_inhibitor" in meds:
        escalation_reasons.append(
            "Kidney disease plus an ACE inhibitor makes electrolyte supplements dangerous and "
            "even vitamin D dosing clinician-managed; defer entirely and refer."
        )
        hits.append(RuleHit(rule_id="ESC-CKD-ACE", action=Action.ESCALATE,
                            subject="CKD + ACE electrolytes", reason=escalation_reasons[-1]))
        recommend_nothing = True
        refer = True

    # High ferritin overload already blocked iron above; it also suppresses recs.
    if ferritin_high:
        escalation_reasons.append(
            "Ferritin is high rather than low: block iron and refer to evaluate possible "
            "overload/hemochromatosis."
        )
        hits.append(RuleHit(rule_id="ESC-IRON-OVERLOAD", action=Action.ESCALATE,
                            subject="iron overload", reason=escalation_reasons[-1]))
        recommend_nothing = True
        refer = True

    # Malabsorptive GI condition (e.g. celiac) driving multiple deficiencies:
    # repletion is still indicated, but the underlying condition needs clinician
    # management, so a referral accompanies the recommendations (does NOT suppress).
    gi_text = " ".join(profile.intake.gi_conditions).lower() + " " + notes.lower()
    if _has(gi_text, "celiac") and not recommend_nothing:
        refer = True
        hits.append(RuleHit(rule_id="RULE-MALABSORPTION-REFER", action=Action.ESCALATE,
                            subject="celiac malabsorption",
                            reason="Multiple deficiencies driven by celiac malabsorption; the "
                                   "underlying GI condition needs clinician management."))
        escalation_reasons.append(
            "Multiple deficiencies driven by celiac malabsorption; repletion is indicated but the "
            "underlying GI condition needs clinician management, so a referral accompanies the recs."
        )

    # Isolated dyslipidemia with no micronutrient gap -> clinician (statin/lifestyle).
    dyslipidemia = _is_dyslipidemia(labs, demo.sex)

    # ----------------------------------------------------------------- #
    # STEP 3 — Candidate deficiency RECOMMENDATIONS
    # (skipped entirely when a suppressing escalation fired)
    # ----------------------------------------------------------------- #
    blocked = {canonical(b.supplement) for b in blocks}

    if not recommend_nothing:
        candidates: list[tuple[str, str, str]] = []  # (display, reason, rule_id)

        # --- Pregnancy / preconception folate (standard of care, not a deficiency) ---
        if pregnant:
            candidates.append((
                "folate (folic acid)",
                "Pregnancy: neural-tube-defect prevention (standard of care)."
                + (f" Folate {labs.folate.value} ng/mL at the low end."
                   if labs.folate.value < 7 else ""),
                "RULE-PREG-FOLATE",
            ))
        elif planning:
            candidates.append((
                "folic acid",
                "Preconception: folic acid reduces neural-tube-defect risk; start before "
                f"conception. Folate {labs.folate.value} ng/mL at the low edge.",
                "RULE-PRECONCEPTION-FOLATE",
            ))
        elif labs.folate.value < rr.FOLATE_DEFICIENT:
            candidates.append((
                "folate",
                f"Folate {labs.folate.value} ng/mL — deficient.",
                "RULE-FOLATE-LOW",
            ))

        # --- Iron ---
        iron_deficient = labs.ferritin.value < rr.FERRITIN_DEFICIENT
        if iron_deficient:
            supp = "prenatal iron" if pregnant else "iron"
            cause = ""
            if _has(notes, "menstrual"):
                cause = " menstrual loss."
            elif "celiac" in " ".join(profile.intake.gi_conditions).lower() or _has(notes, "celiac"):
                cause = " from malabsorption."
            elif pregnant:
                cause = " with increased pregnancy demand."
            candidates.append((
                supp,
                f"Ferritin {labs.ferritin.value} ng/mL — iron deficiency;{cause}".rstrip(";").strip()
                if cause else f"Ferritin {labs.ferritin.value} ng/mL — iron deficiency.",
                "RULE-IRON-LOW",
            ))

        # --- B12 ---
        b12 = labs.b12.value
        dietary_risk = diet in ("vegan", "vegetarian")
        if "metformin" in meds and b12 < rr.B12_BORDERLINE:
            candidates.append((
                "vitamin B12",
                f"B12 {b12} pg/mL. {METFORMIN_B12.reason}",
                METFORMIN_B12.rule_id,
            ))
        elif b12 < rr.B12_DEFICIENT:
            reason = f"B12 {b12} pg/mL — low."
            if diet == "vegan":
                reason = f"B12 {b12} pg/mL on a vegan diet — dietary deficiency, clearly indicated."
            elif _has(notes, "celiac") or "celiac" in " ".join(profile.intake.gi_conditions).lower():
                reason = f"B12 {b12} pg/mL — low (malabsorption)."
            candidates.append(("vitamin B12", reason, "RULE-B12-LOW"))
        elif b12 < rr.B12_BORDERLINE and dietary_risk:
            candidates.append((
                "vitamin B12",
                f"B12 {b12} pg/mL — borderline low on a {diet} diet.",
                "RULE-B12-BORDERLINE-DIET",
            ))

        # --- Vitamin D ---
        vitd = labs.vitamin_d_25oh.value
        vitd_act = rr.VITD_PREGNANCY_ACT if pregnant else rr.VITD_INSUFFICIENT
        if vitd < vitd_act:
            if vitd < rr.VITD_DEFICIENT:
                dstate = "deficient"
            else:
                dstate = "insufficient"
            supp = "vitamin D3"
            if "thiazide" in meds:  # P18: emphasise standard (not high) dose alongside a Ca block
                supp = "vitamin D3 (standard dose)"
            cause = ""
            if _has(notes, "low sun") or profile.intake.sun_exposure in ("low", "very_low"):
                if vitd < rr.VITD_DEFICIENT:
                    cause = " low sun." if diet not in ("vegetarian",) else " low sun, vegetarian."
            candidates.append((
                supp,
                f"25-OH D {vitd} ng/mL — {dstate}." + (f"{cause}" if cause else ""),
                "RULE-VITD-LOW",
            ))

        # Drop candidates that are contraindicated by a block.
        for display, reason, rid in candidates:
            if canonical(display) in blocked:
                continue
            add_rec(display, reason, rid)

    # ----------------------------------------------------------------- #
    # STEP 4 — TIMING cautions
    # ----------------------------------------------------------------- #
    rec_canon = {canonical(r.supplement) for r in recs}
    if "levothyroxine" in meds and "iron" in rec_canon:
        add_timing(LEVO_IRON_TIMING)

    # ----------------------------------------------------------------- #
    # STEP 5 — PRIORITY ORDERING (a safety property)
    # ----------------------------------------------------------------- #
    # priority_order is only meaningful when there is a genuine conflict (2+ recs).
    priority = _order_priority(recs, labs=labs, pregnant=pregnant, planning=planning, hits=hits)

    # ----------------------------------------------------------------- #
    # STEP 6 — Isolated dyslipidemia / prediabetes referrals
    # ----------------------------------------------------------------- #
    if not recs and not blocks and not recommend_nothing:
        if dyslipidemia:
            refer = True
            recommend_nothing = True
            escalation_reasons.append(
                "High LDL / low HDL is a cardiovascular-risk matter for a clinician (statin "
                "decision, lifestyle), not a micronutrient supplement problem."
            )
            hits.append(RuleHit(rule_id="ESC-DYSLIPIDEMIA", action=Action.ESCALATE,
                                subject="dyslipidemia", reason=escalation_reasons[-1]))
        elif rr.HBA1C_PREDIABETES <= labs.hba1c.value < rr.HBA1C_DIABETES:
            recommend_nothing = True
            escalation_reasons.append(
                f"HbA1c {labs.hba1c.value}% is prediabetes — addressed by lifestyle and clinician "
                f"follow-up, not a supplement. No micronutrient deficiency present."
            )
            hits.append(RuleHit(rule_id="RULE-PREDIABETES-NOSUPP", action=Action.ESCALATE,
                                subject="prediabetes", reason=escalation_reasons[-1]))
        else:
            recommend_nothing = True
            hits.append(RuleHit(rule_id="RULE-NO-TRIGGER", action=Action.ESCALATE,
                                subject="no deficiency",
                                reason="No value crosses an age/sex-aware threshold; nothing indicated."))
            escalation_reasons.append(
                "No value crosses an age/sex-aware threshold — no supplement is indicated."
            )

    # If a suppressing escalation zeroed recs, ensure recommend_nothing is set
    # only when there is genuinely nothing to recommend.
    if recommend_nothing:
        recs = []
        priority = []

    # ----------------------------------------------------------------- #
    # STEP 7 — Rationale (deterministic template from fired hits)
    # ----------------------------------------------------------------- #
    rationale = _render_rationale(
        recs=recs, blocks=blocks, timings=timings, priority=priority,
        refer=refer, recommend_nothing=recommend_nothing,
        escalation_reasons=escalation_reasons,
    )

    return EngineDecision(
        recommend=recs,
        priority_order=priority,
        block=blocks,
        timing_cautions=timings,
        refer_to_clinician=refer,
        recommend_nothing=recommend_nothing,
        rationale=rationale,
        rule_hits=hits,
    )


# --------------------------------------------------------------------------- #
# Priority policy
# --------------------------------------------------------------------------- #
def _order_priority(recs, *, labs, pregnant: bool, planning: bool, hits) -> list[str]:
    """Order recommended supplements by the safety priority policy.

    priority_order is only surfaced when 2+ supplements are recommended (a real
    conflict). Policy:

      * Pregnancy / preconception -> folate first, then iron, then vitamin D.
      * Otherwise:
          - iron is always first (most symptomatic; highest anemia risk),
          - then frank deficiencies rank ahead of merely-borderline ones,
          - within a tier the fixed clinical order is B12, folate, vitamin D,
          - and B12 must precede folate whenever both are recommended (correcting
            folate alone can mask a B12 deficiency — a safety property, enforced).
    """
    names = [r.supplement for r in recs]
    if len(names) < 2:
        return []

    canon = {n: canonical(n) for n in names}

    # Deficiency "frankness": frank (below the hard-low cutoff) sorts ahead of
    # borderline. B12 210 (borderline) must sit behind a frank vitamin D, etc.
    def is_frank(c: str) -> bool:
        if c == "vitamin_b12":
            return labs.b12.value < rr.B12_DEFICIENT
        if c == "vitamin_d":
            return labs.vitamin_d_25oh.value < rr.VITD_DEFICIENT
        if c == "folate":
            return labs.folate.value < rr.FOLATE_DEFICIENT
        return True  # iron / pregnancy folate treated as frank

    category = {"vitamin_b12": 0, "folate": 1, "vitamin_d": 2}

    def rank(n: str) -> tuple:
        c = canon[n]
        if pregnant or planning:
            preg_order = {"folate": 0, "iron": 1, "vitamin_d": 2, "vitamin_b12": 3}
            return (preg_order.get(c, 99),)
        if c == "iron":
            return (0, 0, 0)
        # tier 0 = frank, tier 1 = borderline; then fixed category order.
        return (1, 0 if is_frank(c) else 1, category.get(c, 99))

    ordered = sorted(names, key=lambda n: rank(n) + (names.index(n),))

    # Hard safety enforcement: B12 before folate whenever both are present.
    if "vitamin_b12" in canon.values() and "folate" in canon.values():
        b12_name = next(n for n in ordered if canon[n] == "vitamin_b12")
        fol_name = next(n for n in ordered if canon[n] == "folate")
        if ordered.index(b12_name) > ordered.index(fol_name):
            ordered.remove(b12_name)
            ordered.insert(ordered.index(fol_name), b12_name)
        hits.append(RuleHit(rule_id=B12_BEFORE_FOLATE.rule_id, action=Action.TIMING_CAUTION,
                            subject="priority", reason=B12_BEFORE_FOLATE.reason))

    return ordered


def _is_dyslipidemia(labs, sex: str) -> bool:
    hdl_low = rr.HDL_LOW_MALE if sex == "male" else rr.HDL_LOW_FEMALE
    return labs.ldl.value >= rr.LDL_HIGH and labs.hdl.value <= hdl_low


# --------------------------------------------------------------------------- #
# Rationale rendering (template strings — NOT an LLM)
# --------------------------------------------------------------------------- #
def _render_rationale(*, recs, blocks, timings, priority, refer, recommend_nothing,
                      escalation_reasons) -> str:
    parts: list[str] = []
    for r in escalation_reasons:
        parts.append(r)
    if recs:
        if priority:
            parts.append("Recommended (in priority order): " + ", ".join(priority) + ".")
        else:
            parts.append("Recommended: " + ", ".join(r.supplement for r in recs) + ".")
    if blocks:
        parts.append("Blocked: " + "; ".join(f"{b.supplement} — {b.reason}" for b in blocks))
    if timings:
        parts.append("Timing: " + "; ".join(f"{t.supplement} — {t.caution}" for t in timings))
    if refer:
        parts.append("Refer to a clinician.")
    if recommend_nothing and not recs:
        parts.append("No supplement is recommended.")
    return " ".join(parts).strip() or "No rule fired."
