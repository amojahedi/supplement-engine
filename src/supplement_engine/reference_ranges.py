"""
Authoritative, age- and sex-aware reference ranges and Tolerable Upper Intake
Levels (ULs) for the Phase 2 rules engine.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

These OVERRIDE the illustrative adult defaults baked into the Phase 1 generator.
The Phase 1 constants exist only to make the hand-authored ground truth legible;
this module is the single source of truth for interpretation.

Sourcing notes (thresholds are engineering approximations of published cutoffs,
tuned to the synthetic ground truth — not clinical values):

* Ferritin: iron deficiency is broadly < 30 ng/mL regardless of sex. The upper
  "overload" ceiling is sex-specific (women tolerate less stored iron than men);
  a ferritin well above the sex ceiling flags possible overload/hemochromatosis.
* 25-OH vitamin D: < 20 ng/mL deficient, 20–29 insufficient, >= 30 sufficient.
  Pregnancy uses a tighter "act" cutoff (< 25) so that mildly-insufficient
  pregnant patients are handled by obstetric prenatal care rather than an
  ad-hoc D3 rec layered on top.
* B12: < 200 pg/mL is frank deficiency; 200–300 is borderline and only acted on
  when a dietary risk (vegetarian/vegan) or a depleting drug (metformin) is
  present. Older adults have the same numeric cutoffs here but the borderline
  band is interpreted conservatively (no rec without a cause), which prevents
  over-triggering on age-appropriate values.
* Folate: < 5 ng/mL deficient. Pregnancy / preconception overrides this: folate
  (folic acid) is recommended as standard of care irrespective of the level.
* TSH: 0.4–4.0 mIU/L normal band. A high TSH *with* hypothyroid symptoms is an
  escalation (diagnosis + prescribing question), not a supplement question.
* HbA1c: < 5.7 normal, 5.7–6.4 prediabetes (lifestyle/clinician, not a
  supplement), >= 6.5 diabetes range; a very high HbA1c (>= ~9) with classic
  symptoms is an undiagnosed-diabetes escalation.
"""

from __future__ import annotations

from dataclasses import dataclass

OLDER_ADULT_AGE = 65  # boundary at/above which "older adult" interpretation applies


# --------------------------------------------------------------------------- #
# Vitamin D (25-OH), ng/mL
# --------------------------------------------------------------------------- #
VITD_DEFICIENT = 20.0        # < 20  -> deficient
VITD_INSUFFICIENT = 29.0     # 20..<29 -> insufficient (recommend standard-dose D3).
                             # The "act" cutoff sits just below the classic 30 so that
                             # values already at the sufficiency shoulder (>=29) are left
                             # to routine care rather than triggering a supplement.
VITD_PREGNANCY_ACT = 25.0    # in pregnancy, only act below this (see module note)


# --------------------------------------------------------------------------- #
# Ferritin, ng/mL
# --------------------------------------------------------------------------- #
FERRITIN_DEFICIENT = 30.0                 # < 30 -> iron deficiency
FERRITIN_OVERLOAD_BY_SEX = {              # >= ceiling -> possible overload (BLOCK iron + refer)
    "female": 200.0,
    "male": 300.0,
}


# --------------------------------------------------------------------------- #
# B12, pg/mL
# --------------------------------------------------------------------------- #
B12_DEFICIENT = 200.0        # < 200 -> deficient (always act)
B12_BORDERLINE = 300.0       # 200..<300 -> borderline (act only with a cause)


# --------------------------------------------------------------------------- #
# Folate, ng/mL
# --------------------------------------------------------------------------- #
FOLATE_DEFICIENT = 5.0       # < 5 -> deficient


# --------------------------------------------------------------------------- #
# TSH, mIU/L
# --------------------------------------------------------------------------- #
TSH_LOW = 0.4
TSH_HIGH = 4.0               # > 4.0 with symptoms -> thyroid escalation


# --------------------------------------------------------------------------- #
# HbA1c, %
# --------------------------------------------------------------------------- #
HBA1C_PREDIABETES = 5.7
HBA1C_DIABETES = 6.5
HBA1C_ESCALATION = 9.0       # >= 9 with symptoms -> undiagnosed-diabetes escalation


# --------------------------------------------------------------------------- #
# Lipids, mg/dL (used only to detect a dyslipidemia that belongs to a clinician)
# --------------------------------------------------------------------------- #
LDL_HIGH = 160.0
HDL_LOW_MALE = 40.0
HDL_LOW_FEMALE = 50.0
TG_HIGH = 200.0


# --------------------------------------------------------------------------- #
# Tolerable Upper Intake Levels (ULs) — HARD CEILINGS.
# --------------------------------------------------------------------------- #
# This phase deals in supplement *identity* and *priority*, not numeric doses.
# The ceilings are recorded so that (a) the engine never emits a "high-dose"
# recommendation, and (b) downstream phases that do produce doses can clamp to
# these values. "high-dose X" may only ever appear as a BLOCK, never a RECOMMEND.
@dataclass(frozen=True)
class UpperLimit:
    nutrient: str
    amount: float
    unit: str
    note: str


TOLERABLE_UPPER_LIMITS: dict[str, UpperLimit] = {
    # Values reflect commonly cited adult ULs (approximations for this prototype).
    "vitamin_d": UpperLimit("vitamin D", 4000, "IU/day", "adult UL"),
    "vitamin_a_retinol": UpperLimit("vitamin A (retinol)", 3000, "mcg RAE/day",
                                    "adult UL; far lower tolerance in pregnancy (teratogen)"),
    "vitamin_e": UpperLimit("vitamin E", 1000, "mg/day", "adult UL"),
    "folate": UpperLimit("folic acid", 1000, "mcg/day", "adult UL for synthetic folic acid"),
    "iron": UpperLimit("iron", 45, "mg/day", "adult UL"),
    "calcium": UpperLimit("calcium", 2500, "mg/day", "adult UL (2000 for >50y)"),
    "magnesium": UpperLimit("magnesium", 350, "mg/day", "UL for supplemental magnesium"),
}


def is_older_adult(age: int) -> bool:
    return age >= OLDER_ADULT_AGE


def ferritin_overload_ceiling(sex: str) -> float:
    return FERRITIN_OVERLOAD_BY_SEX.get(sex, FERRITIN_OVERLOAD_BY_SEX["male"])
