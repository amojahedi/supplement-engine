"""
Phase 1 — Synthetic patient profile generator.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
Every profile below is fabricated for engineering a safety-in-code reasoning
engine. None of it describes a real person and none of it is clinical guidance.

Design notes
------------
* Reproducible generation = fully deterministic. There is NO randomness; the
  script emits the same JSON on every run. Ground truth is hand-authored per
  profile (Phase 1 requires hand-written expected output), so profiles are
  curated rather than sampled. A sha256 of the serialized output is printed so
  the artifact can be pinned in eval.
* Reference ranges here are adult defaults used only to make the ground truth
  legible. The Phase 2 rules engine owns the *authoritative*, age/sex-aware
  ranges and Tolerable Upper Intake Levels; do not treat these constants as the
  source of truth.

Units are attached to every lab value on purpose: mg/dL vs nmol/L (etc.) is a
~2.5x silent error, and extraction (Phase 2) must reject ambiguity rather than
guess.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "phase1-v1"

# --- Reference ranges (adult defaults; illustrative only) --------------------
# Not authoritative. The rules engine (Phase 2) is the source of truth.
REFERENCE_RANGES = {
    "ferritin":         {"unit": "ng/mL", "low": 30,   "high_f": 200, "high_m": 400,
                         "note": "iron deficiency < 30; overload risk when high"},
    "vitamin_d_25oh":   {"unit": "ng/mL", "deficient": 20, "insufficient": 30, "high": 100},
    "b12":              {"unit": "pg/mL", "low": 200,  "borderline": 300, "high": 900},
    "folate":           {"unit": "ng/mL", "low": 4,    "high": 20},
    "tsh":              {"unit": "mIU/L", "low": 0.4,  "high": 4.0,
                         "note": "subclinical vs overt thresholds owned by rules engine"},
    "hba1c":            {"unit": "%",     "normal": 5.7, "prediabetes": 6.5},
    "lipids":           {"unit": "mg/dL"},
}


def labs(ferritin, vitd, b12, folate, tsh, hba1c, total_chol, ldl, hdl, tg):
    """Attach units to every value. Ambiguous units are a silent 2.5x error."""
    return {
        "ferritin":       {"value": ferritin, "unit": "ng/mL"},
        "vitamin_d_25oh": {"value": vitd,     "unit": "ng/mL"},
        "b12":            {"value": b12,      "unit": "pg/mL"},
        "folate":         {"value": folate,   "unit": "ng/mL"},
        "tsh":            {"value": tsh,      "unit": "mIU/L"},
        "hba1c":          {"value": hba1c,    "unit": "%"},
        "lipids": {
            "total_chol":    {"value": total_chol, "unit": "mg/dL"},
            "ldl":           {"value": ldl,        "unit": "mg/dL"},
            "hdl":           {"value": hdl,        "unit": "mg/dL"},
            "triglycerides": {"value": tg,         "unit": "mg/dL"},
        },
    }


def demo(age, sex, pregnant=False):
    return {"age": age, "sex": sex, "pregnant": pregnant}


def intake(diet, sun, gi=None, pregnancy_status="not_pregnant", notes=""):
    return {
        "diet": diet,
        "sun_exposure": sun,
        "gi_conditions": gi or [],
        "pregnancy_status": pregnancy_status,
        "notes": notes,
    }


def out(recommend=None, priority=None, block=None, timing=None,
        refer=False, recommend_nothing=False, rationale=""):
    return {
        "recommend": recommend or [],
        "priority_order": priority or [],
        "block": block or [],
        "timing_cautions": timing or [],
        "refer_to_clinician": refer,
        "recommend_nothing": recommend_nothing,
        "rationale": rationale,
    }


# --- The 30 profiles ---------------------------------------------------------
# Coverage tags used by the eval + frontend badges:
#   conflicting_priority, contraindication_block, in_range_no_trigger,
#   referral_recommend_nothing, pregnancy
PROFILES = [
    {
        "profile_id": "P01",
        "tags": ["conflicting_priority"],
        "demographics": demo(34, "female"),
        "labs": labs(12, 18, 210, 6, 2.1, 5.3, 180, 100, 55, 90),
        "medications": [],
        "intake": intake("vegetarian", "low",
                         notes="Fatigue, heavy menstrual periods."),
        "expected_output": out(
            recommend=[
                {"supplement": "iron", "reason": "Ferritin 12 ng/mL — iron deficiency; menstrual loss."},
                {"supplement": "vitamin D3", "reason": "25-OH D 18 ng/mL — deficient; low sun, vegetarian."},
                {"supplement": "vitamin B12", "reason": "B12 210 pg/mL — borderline low on vegetarian diet."},
            ],
            priority=["iron", "vitamin D3", "vitamin B12"],
            rationale="Three deficits; iron is prioritized as most symptomatic and "
                      "at highest risk of progressing to anemia. Priority ordering matters.",
        ),
    },
    {
        "profile_id": "P02",
        "tags": ["contraindication_block"],
        "demographics": demo(58, "male"),
        "labs": labs(120, 34, 500, 10, 1.8, 5.5, 240, 150, 38, 320),
        "medications": ["warfarin"],
        "intake": intake("mixed", "moderate",
                         notes="Elevated triglycerides; asks about fish oil."),
        "expected_output": out(
            block=[
                {"supplement": "high-dose omega-3 (fish oil)",
                 "reason": "Supplement–medication interaction with warfarin: additive bleeding risk. "
                           "The otherwise-obvious rec for TG 320 is blocked."},
            ],
            refer=True,
            rationale="High triglycerides would ordinarily suggest omega-3, but warfarin "
                      "makes that unsafe without clinician oversight. Contraindication overrides "
                      "the obvious recommendation.",
        ),
    },
    {
        "profile_id": "P03",
        "tags": ["in_range_no_trigger"],
        "demographics": demo(41, "male"),
        "labs": labs(32, 31, 205, 5, 3.9, 5.6, 185, 110, 50, 120),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Routine check, feels well."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="Every value sits just inside range (ferritin 32, D 31, B12 205, "
                      "TSH 3.9, HbA1c 5.6). Nothing crosses a threshold — no supplement is "
                      "indicated. Guards against false-positive triggering on near-boundary values.",
        ),
    },
    {
        "profile_id": "P04",
        "tags": ["referral_recommend_nothing"],
        "demographics": demo(52, "male"),
        "labs": labs(90, 28, 400, 9, 2.4, 10.1, 210, 130, 40, 180),
        "medications": [],
        "intake": intake("mixed", "moderate",
                         notes="Increased thirst, weight loss, blurry vision. No diabetes diagnosis."),
        "expected_output": out(
            refer=True,
            recommend_nothing=True,
            rationale="HbA1c 10.1% with classic symptoms indicates likely undiagnosed diabetes. "
                      "This is a medical diagnosis, not a supplement problem. Escalation rule forces "
                      "clinician referral and suppresses all other output.",
        ),
    },
    {
        "profile_id": "P05",
        "tags": ["pregnancy", "contraindication_block"],
        "demographics": demo(29, "female", pregnant=True),
        "labs": labs(18, 22, 350, 5, 1.9, 5.1, 175, 95, 62, 110),
        "medications": [],
        "intake": intake("mixed", "low", pregnancy_status="pregnant_12_weeks",
                         notes="First trimester. Not yet on a prenatal vitamin."),
        "expected_output": out(
            recommend=[
                {"supplement": "folate (folic acid)",
                 "reason": "Pregnancy: neural-tube-defect prevention; folate 5 ng/mL at low end."},
                {"supplement": "prenatal iron",
                 "reason": "Ferritin 18 ng/mL with increased pregnancy demand."},
                {"supplement": "vitamin D3",
                 "reason": "25-OH D 22 ng/mL — insufficient; low sun."},
            ],
            priority=["folate (folic acid)", "prenatal iron", "vitamin D3"],
            block=[
                {"supplement": "high-dose vitamin A (retinol)",
                 "reason": "Teratogenic in pregnancy — supplement–condition contraindication."},
            ],
            refer=True,
            rationale="Pregnancy case: folate is the priority. High-dose vitamin A is hard-blocked. "
                      "All recommendations must be delivered under obstetric care, so a clinician "
                      "referral accompanies the output.",
        ),
    },
    {
        "profile_id": "P06",
        "tags": ["contraindication_block"],  # here: interaction-driven recommend, not block
        "demographics": demo(61, "female"),
        "labs": labs(80, 33, 180, 8, 2.0, 6.8, 190, 105, 52, 140),
        "medications": ["metformin"],
        "intake": intake("mixed", "moderate", notes="Type 2 diabetes, well-controlled."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin B12",
                 "reason": "B12 180 pg/mL. Metformin is a documented cause of B12 depletion "
                           "(supplement–medication interaction working in the deficiency direction)."},
            ],
            rationale="Metformin lowers B12 absorption; the low B12 is explained by the medication "
                      "and B12 repletion is indicated. HbA1c 6.8% is an existing, managed diagnosis — "
                      "no referral needed for that alone.",
        ),
    },
    {
        "profile_id": "P07",
        "tags": [],
        "demographics": demo(45, "female"),
        "labs": labs(14, 29, 420, 11, 3.2, 5.4, 195, 115, 58, 100),
        "medications": ["levothyroxine"],
        "intake": intake("mixed", "moderate", notes="Hypothyroid, stable on levothyroxine."),
        "expected_output": out(
            recommend=[
                {"supplement": "iron", "reason": "Ferritin 14 ng/mL — iron deficiency."},
            ],
            timing=[
                {"supplement": "iron",
                 "caution": "Separate iron from levothyroxine by >=4 hours — iron chelates and "
                            "reduces levothyroxine absorption (supplement–medication interaction)."},
            ],
            rationale="Iron is indicated, but administration timing must avoid the levothyroxine "
                      "absorption interaction. Recommendation ships with a timing caution, not a block.",
        ),
    },
    {
        "profile_id": "P08",
        "tags": ["contraindication_block"],
        "demographics": demo(37, "male"),
        "labs": labs(95, 30, 480, 12, 1.6, 5.2, 200, 120, 50, 130),
        "medications": ["sertraline"],
        "intake": intake("mixed", "moderate",
                         notes="Currently self-medicating with St John's Wort for mood."),
        "expected_output": out(
            block=[
                {"supplement": "St John's Wort",
                 "reason": "Supplement–medication interaction with sertraline (SSRI): serotonin "
                           "syndrome risk. Must be stopped."},
            ],
            refer=True,
            rationale="Active dangerous interaction already in progress. Block St John's Wort and "
                      "refer to the prescribing clinician. No new supplement is added on top.",
        ),
    },
    {
        "profile_id": "P09",
        "tags": [],
        "demographics": demo(26, "female"),
        "labs": labs(45, 27, 150, 9, 2.2, 5.0, 170, 90, 60, 80),
        "medications": [],
        "intake": intake("vegan", "moderate", notes="Vegan 4 years."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin B12",
                 "reason": "B12 150 pg/mL on a vegan diet — dietary deficiency, clearly indicated."},
                {"supplement": "vitamin D3",
                 "reason": "25-OH D 27 ng/mL — insufficient."},
            ],
            priority=["vitamin B12", "vitamin D3"],
            rationale="Classic vegan B12 deficiency plus insufficient vitamin D. Straightforward "
                      "dietary-gap repletion.",
        ),
    },
    {
        "profile_id": "P10",
        "tags": [],
        "demographics": demo(33, "male"),
        "labs": labs(70, 15, 500, 14, 1.9, 5.3, 180, 100, 55, 95),
        "medications": [],
        "intake": intake("mixed", "very_low", notes="Indoor office worker, minimal sun."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin D3",
                 "reason": "25-OH D 15 ng/mL — deficient; very low sun exposure."},
            ],
            rationale="Single clear deficiency (vitamin D) with a matching lifestyle cause.",
        ),
    },
    {
        "profile_id": "P11",
        "tags": [],
        "demographics": demo(23, "female"),
        "labs": labs(8, 32, 400, 10, 2.1, 5.1, 165, 85, 63, 75),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Heavy menstrual bleeding, fatigue."),
        "expected_output": out(
            recommend=[
                {"supplement": "iron",
                 "reason": "Ferritin 8 ng/mL — marked iron deficiency; menstrual loss."},
            ],
            rationale="Isolated, marked iron deficiency with a clear cause.",
        ),
    },
    {
        "profile_id": "P12",
        "tags": ["in_range_no_trigger"],
        "demographics": demo(72, "male"),
        "labs": labs(140, 35, 340, 12, 2.5, 5.6, 185, 108, 48, 130),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Age-aware ranges apply."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="B12 340 pg/mL is adequate; all values are appropriate for a 72-year-old. "
                      "Nothing crosses an age-aware threshold — no supplement indicated.",
        ),
    },
    {
        "profile_id": "P13",
        "tags": ["conflicting_priority"],
        "demographics": demo(39, "female"),
        "labs": labs(11, 17, 190, 3, 2.3, 5.2, 160, 88, 57, 85),
        "medications": [],
        "intake": intake("mixed", "low", gi=["celiac_disease"],
                         notes="Newly managed celiac; malabsorption pattern."),
        "expected_output": out(
            recommend=[
                {"supplement": "iron", "reason": "Ferritin 11 — deficiency from malabsorption."},
                {"supplement": "folate", "reason": "Folate 3 ng/mL — deficient."},
                {"supplement": "vitamin D3", "reason": "25-OH D 17 — deficient."},
                {"supplement": "vitamin B12", "reason": "B12 190 — low."},
            ],
            priority=["iron", "folate", "vitamin B12", "vitamin D3"],
            refer=True,
            rationale="Multiple deficiencies driven by celiac malabsorption. Repletion is indicated "
                      "but the underlying GI condition needs clinician management, so a referral "
                      "accompanies the recommendations.",
        ),
    },
    {
        "profile_id": "P14",
        "tags": ["contraindication_block", "referral_recommend_nothing"],
        "demographics": demo(54, "female"),
        "labs": labs(60, 26, 410, 3, 2.0, 5.5, 200, 118, 54, 140),
        "medications": ["methotrexate"],
        "intake": intake("mixed", "moderate", notes="Rheumatoid arthritis on methotrexate."),
        "expected_output": out(
            block=[
                {"supplement": "self-directed folate/folic acid",
                 "reason": "Folate dosing/timing around methotrexate is therapeutically coupled and "
                           "clinician-managed (supplement–medication interaction). Do not self-start."},
            ],
            refer=True,
            recommend_nothing=True,
            rationale="Low folate would normally prompt folate, but with methotrexate the folate "
                      "regimen is part of the drug therapy and must be set by the prescriber. Defer "
                      "entirely to the clinician.",
        ),
    },
    {
        "profile_id": "P15",
        "tags": [],
        "demographics": demo(48, "male"),
        "labs": labs(110, 30, 460, 13, 2.1, 6.1, 205, 125, 44, 165),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Prediabetic range HbA1c."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="HbA1c 6.1% is prediabetes — addressed by lifestyle and clinician follow-up, "
                      "not a supplement. No micronutrient deficiency present, so no supplement is "
                      "recommended (lifestyle counseling noted outside supplement scope).",
        ),
    },
    {
        "profile_id": "P16",
        "tags": ["pregnancy", "contraindication_block"],
        "demographics": demo(31, "female", pregnant=True),
        "labs": labs(40, 25, 380, 8, 1.7, 5.0, 178, 96, 60, 120),
        "medications": [],
        "intake": intake("mixed", "moderate", pregnancy_status="pregnant_20_weeks",
                         notes="Already taking a high-dose retinol (vitamin A) beauty supplement."),
        "expected_output": out(
            recommend=[
                {"supplement": "folate (folic acid)", "reason": "Pregnancy standard of care."},
            ],
            block=[
                {"supplement": "high-dose vitamin A (retinol)",
                 "reason": "Teratogenic — must stop. Supplement–condition contraindication (pregnancy)."},
            ],
            refer=True,
            rationale="Second pregnancy case with an active teratogen exposure. Hard-block retinol, "
                      "continue folate, and refer for obstetric review of the exposure.",
        ),
    },
    {
        "profile_id": "P17",
        "tags": ["contraindication_block"],
        "demographics": demo(66, "male"),
        "labs": labs(130, 24, 470, 11, 2.2, 5.7, 210, 128, 46, 150),
        "medications": ["warfarin"],
        "intake": intake("mixed", "low",
                         notes="Asks about vitamin K and vitamin E for 'general health'."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin D3", "reason": "25-OH D 24 ng/mL — insufficient; low sun."},
            ],
            block=[
                {"supplement": "vitamin K supplement",
                 "reason": "Antagonizes warfarin — destabilizes INR (supplement–medication interaction)."},
                {"supplement": "high-dose vitamin E",
                 "reason": "Additive bleeding risk with warfarin."},
            ],
            rationale="Vitamin D is safe to recommend; vitamin K and high-dose vitamin E are blocked "
                      "due to warfarin. Counsel dietary vitamin K consistency (handled by clinician).",
        ),
    },
    {
        "profile_id": "P18",
        "tags": ["contraindication_block"],
        "demographics": demo(59, "female"),
        "labs": labs(95, 21, 430, 12, 2.4, 5.6, 215, 130, 55, 140),
        "medications": ["hydrochlorothiazide"],
        "intake": intake("mixed", "low", notes="Wants a high-dose calcium + vitamin D bone product."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin D3 (standard dose)",
                 "reason": "25-OH D 21 ng/mL — insufficient."},
            ],
            block=[
                {"supplement": "high-dose calcium",
                 "reason": "Thiazide reduces calcium excretion — hypercalcemia risk "
                           "(supplement–medication interaction). Hard ceiling applies."},
            ],
            rationale="Vitamin D repletion is fine; high-dose calcium is blocked because "
                      "hydrochlorothiazide predisposes to hypercalcemia.",
        ),
    },
    {
        "profile_id": "P19",
        "tags": ["in_range_no_trigger"],
        "demographics": demo(25, "female"),
        "labs": labs(60, 45, 550, 15, 1.8, 5.0, 165, 85, 65, 70),
        "medications": [],
        "intake": intake("mixed", "high", notes="Healthy, active, balanced diet."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="All labs comfortably normal. No deficiency, no risk factor — no supplement.",
        ),
    },
    {
        "profile_id": "P20",
        "tags": [],
        "demographics": demo(50, "male"),
        "labs": labs(150, 32, 500, 13, 2.0, 5.5, 245, 165, 36, 190),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Dyslipidemia; no micronutrient deficiency."),
        "expected_output": out(
            recommend_nothing=True,
            refer=True,
            rationale="High LDL / low HDL is a cardiovascular-risk matter for a clinician "
                      "(statin decision, lifestyle), not a micronutrient supplement problem. "
                      "Refer; recommend no supplement.",
        ),
    },
    {
        "profile_id": "P21",
        "tags": ["conflicting_priority"],
        "demographics": demo(63, "female"),
        "labs": labs(85, 29, 160, 3, 2.1, 5.6, 195, 112, 53, 130),
        "medications": [],
        "intake": intake("mixed", "low", notes="Low B12 and low folate together."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin B12", "reason": "B12 160 pg/mL — low."},
                {"supplement": "folate", "reason": "Folate 3 ng/mL — low."},
            ],
            priority=["vitamin B12", "folate"],
            rationale="Both low, but B12 must be assessed/repleted first: correcting folate alone can "
                      "mask B12 deficiency and allow neurological damage to progress. Priority ordering "
                      "is a safety property, not a preference.",
        ),
    },
    {
        "profile_id": "P22",
        "tags": ["referral_recommend_nothing"],
        "demographics": demo(44, "female"),
        "labs": labs(70, 31, 450, 12, 6.5, 5.3, 180, 100, 58, 95),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Fatigue, cold intolerance. No thyroid diagnosis."),
        "expected_output": out(
            refer=True,
            recommend_nothing=True,
            rationale="TSH 6.5 mIU/L with symptoms suggests subclinical/overt hypothyroidism — a "
                      "diagnostic and prescribing question. No supplement addresses this; refer and "
                      "recommend nothing.",
        ),
    },
    {
        "profile_id": "P23",
        "tags": ["contraindication_block", "referral_recommend_nothing"],
        "demographics": demo(55, "male"),
        "labs": labs(450, 33, 480, 13, 1.9, 5.5, 200, 120, 50, 140),
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Fatigue; self-diagnosed 'low iron', wants iron."),
        "expected_output": out(
            block=[
                {"supplement": "iron",
                 "reason": "Ferritin 450 ng/mL is HIGH — possible iron overload. Iron is contraindicated "
                           "despite the fatigue narrative. Hard block."},
            ],
            refer=True,
            recommend_nothing=True,
            rationale="The intuitive 'tired = take iron' answer is dangerous here: ferritin is high, "
                      "not low. Block iron and refer to evaluate possible overload/hemochromatosis.",
        ),
    },
    {
        "profile_id": "P24",
        "tags": ["contraindication_block"],
        "demographics": demo(69, "male"),
        "labs": labs(120, 19, 500, 12, 2.1, 5.6, 190, 110, 47, 135),
        "medications": ["digoxin"],
        "intake": intake("mixed", "low", notes="Asks about a herbal 'energy' blend containing St John's Wort."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin D3", "reason": "25-OH D 19 ng/mL — deficient."},
            ],
            block=[
                {"supplement": "St John's Wort",
                 "reason": "Reduces digoxin levels (supplement–medication interaction) — risks loss "
                           "of therapeutic effect."},
            ],
            rationale="Vitamin D is indicated and safe; the St John's Wort–containing blend is blocked "
                      "because of the digoxin interaction.",
        ),
    },
    {
        "profile_id": "P25",
        "tags": ["contraindication_block", "referral_recommend_nothing"],
        "demographics": demo(64, "male"),
        "labs": labs(140, 20, 460, 11, 2.3, 6.2, 200, 118, 45, 150),
        "medications": ["lisinopril"],
        "intake": intake("mixed", "low", gi=[], pregnancy_status="not_pregnant",
                         notes="Chronic kidney disease stage 3. Asks about potassium and magnesium."),
        "expected_output": out(
            block=[
                {"supplement": "potassium",
                 "reason": "CKD + ACE inhibitor (lisinopril) → hyperkalemia risk. Hard block."},
                {"supplement": "magnesium",
                 "reason": "Impaired renal clearance in CKD → accumulation risk."},
            ],
            refer=True,
            recommend_nothing=True,
            rationale="Kidney disease plus an ACE inhibitor makes electrolyte supplements dangerous. "
                      "Even vitamin D dosing in CKD is clinician-managed, so defer entirely and refer.",
        ),
    },
    {
        "profile_id": "P26",
        "tags": ["in_range_no_trigger"],
        "demographics": demo(28, "male"),
        "labs": labs(90, 40, 520, 14, 1.7, 5.1, 170, 92, 60, 80),
        "medications": [],
        "intake": intake("mixed", "high", notes="Amateur athlete seeking 'optimization'."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="No deficiency and no risk factor. 'Optimization' with no measured gap is not a "
                      "rule hit — recommend nothing rather than invent a benefit.",
        ),
    },
    {
        "profile_id": "P27",
        "tags": ["pregnancy"],
        "demographics": demo(30, "female"),
        "labs": labs(55, 28, 440, 4, 1.8, 5.0, 172, 94, 61, 90),
        "medications": [],
        "intake": intake("mixed", "moderate", pregnancy_status="planning_pregnancy",
                         notes="Actively trying to conceive."),
        "expected_output": out(
            recommend=[
                {"supplement": "folic acid",
                 "reason": "Preconception: folic acid reduces neural-tube-defect risk; start before "
                           "conception. Folate 4 ng/mL at the low edge."},
                {"supplement": "vitamin D3", "reason": "25-OH D 28 ng/mL — insufficient."},
            ],
            priority=["folic acid", "vitamin D3"],
            rationale="Preconception folic acid is the key evidence-based recommendation. Pregnancy-"
                      "adjacent case where timing (start before conception) matters.",
        ),
    },
    {
        "profile_id": "P28",
        "tags": ["contraindication_block"],
        "demographics": demo(57, "male"),
        "labs": labs(100, 18, 490, 12, 2.0, 5.8, 230, 155, 40, 170),
        "medications": ["atorvastatin"],
        "intake": intake("mixed", "low", notes="Considering St John's Wort for low mood."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin D3", "reason": "25-OH D 18 ng/mL — deficient."},
            ],
            block=[
                {"supplement": "St John's Wort",
                 "reason": "Induces metabolism of atorvastatin, reducing its effect "
                           "(supplement–medication interaction)."},
            ],
            refer=True,
            rationale="Vitamin D is fine to recommend. Block St John's Wort due to the statin "
                      "interaction and refer for the low-mood concern.",
        ),
    },
    {
        "profile_id": "P29",
        "tags": ["referral_recommend_nothing", "conflicting_priority"],
        "demographics": demo(47, "male"),
        "labs": labs(9, 14, 130, 2, 2.2, 5.4, 150, 80, 42, 130),
        "medications": [],
        "intake": intake("mixed", "low", gi=["unexplained_weight_loss"],
                         notes="Multiple severe deficiencies plus unexplained weight loss."),
        "expected_output": out(
            refer=True,
            recommend_nothing=True,
            rationale="Severe multi-nutrient deficiency (iron 9, D 14, B12 130, folate 2) with "
                      "unexplained weight loss points to a systemic underlying cause. Piecemeal "
                      "supplementation would mask a serious workup — refer and recommend nothing.",
        ),
    },
    {
        "profile_id": "P30",
        "tags": ["in_range_no_trigger"],
        "demographics": demo(68, "female"),
        "labs": labs(45, 33, 320, 10, 3.6, 5.6, 210, 120, 58, 150),
        "medications": [],
        "intake": intake("mixed", "moderate",
                         notes="Values that look borderline for a young adult but are age-appropriate."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="TSH 3.6, ferritin 45, B12 320, HbA1c 5.6 are all appropriate for a 68-year-old. "
                      "Age-aware interpretation prevents over-triggering on values that only look "
                      "borderline against young-adult intuitions.",
        ),
    },
]


def build():
    return {
        "schema_version": SCHEMA_VERSION,
        "disclaimer": "SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE. "
                      "Fabricated profiles for engineering a safety-in-code reasoning engine.",
        "reference_ranges_illustrative_only": REFERENCE_RANGES,
        "count": len(PROFILES),
        "profiles": PROFILES,
    }


def main():
    data = build()

    # Integrity checks that must hold before this artifact is usable downstream.
    ids = [p["profile_id"] for p in data["profiles"]]
    assert len(ids) == 30, f"expected 30 profiles, got {len(ids)}"
    assert len(set(ids)) == 30, "duplicate profile_id"
    all_tags = {t for p in data["profiles"] for t in p["tags"]}
    for required in [
        "conflicting_priority", "contraindication_block",
        "in_range_no_trigger", "referral_recommend_nothing", "pregnancy",
    ]:
        assert required in all_tags, f"missing required coverage tag: {required}"

    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "synthetic_profiles.json"

    serialized = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)
    out_path.write_text(serialized + "\n", encoding="utf-8")

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    print(f"wrote {len(ids)} profiles -> {out_path}")
    print(f"sha256: {digest}")
    print(f"coverage tags present: {sorted(all_tags)}")


if __name__ == "__main__":
    main()
