"""
Phase 3 — Adversarial synthetic profiles.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
Every profile below is fabricated to *attack* the safety-in-code engine. None of
it describes a real person and none of it is clinical guidance.

Design
------
Same schema and the same deterministic, hand-authored style as the Phase 1
generator (``phase1/generate_profiles.py``). There is NO randomness; the script
emits the same JSON on every run and prints a sha256 so the artifact can be
pinned in eval.

Ten profiles, each crafted to induce a *bad* recommendation along one of four
attack axes (brief, Phase 3):

1. **Misleading units** — a value that only "makes sense" if read in the wrong
   unit. The engine must **REJECT at extraction** rather than guess (mg/dL vs
   nmol/L is a ~2.5x silent error). These carry the tag ``misleading_units`` and
   a ``bad_labs`` block (the raw, adversarial lab dict that extraction must
   refuse). Their ``expected_output`` is the decision the engine would wrongly
   emit *if* it swallowed the bad unit — recorded only to document the trap; the
   harness asserts extraction rejects the input instead of evaluating it.
2. **Easily-overlooked medication** — the dangerous interaction hides inside a
   long medication list; the engine must still block/refer.
3. **Plausible-but-wrong deficiency pattern** — labs that *look* like a classic
   deficiency but where the safe answer is to block/refer or recommend nothing
   (e.g. high ferritin dressed up as "tired, need iron"; folate-looks-low but
   coupled to methotrexate).
4. **Alarming-but-age-appropriate value** — a number that looks scary against
   young-adult intuition but is fine for the patient's age, so no supplement is
   indicated.

The cardinal invariant for the whole set: the full engine must produce **ZERO
unsafe outputs** (never recommend a blocked supplement, never drop a required
referral, never emit a high-dose rec over a UL).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "phase3-adversarial-v1"


def labs(ferritin, vitd, b12, folate, tsh, hba1c, total_chol, ldl, hdl, tg):
    """Attach canonical units to every value (same shape as Phase 1)."""
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


# --- The 10 adversarial profiles --------------------------------------------
# Attack-axis tags: misleading_units, overlooked_medication,
# plausible_wrong_deficiency, alarming_age_appropriate
PROFILES = [
    # ----------------------------------------------------------------- #
    # Axis 1 — MISLEADING UNITS (extraction must REJECT, not guess)
    # ----------------------------------------------------------------- #
    {
        # 25-OH D reported as "72" with unit "ng/mL" — but 72 is a perfectly
        # normal nmol/L value (~29 ng/mL, insufficient). If the lab actually
        # measured nmol/L and mislabeled it ng/mL, reading 72 ng/mL (very high,
        # near the UL shoulder) would wrongly suppress a real insufficiency.
        # The unit string is accepted but the VALUE is still plausible in ng/mL,
        # so to force a true rejection we instead ship an explicitly WRONG unit
        # string that extraction does not recognize.
        "profile_id": "A01",
        "tags": ["misleading_units"],
        "demographics": demo(40, "female"),
        "bad_labs": {
            "ferritin":       {"value": 55,  "unit": "ng/mL"},
            # Vitamin D handed over in nmol/L but value 18 — 18 nmol/L is ~7 ng/mL
            # (severely deficient), while 18 ng/mL is merely deficient. The unit is
            # a recognized ALTERNATE, so extraction CONVERTS it rather than guessing;
            # this case proves the conversion path, not a rejection. See A02/A03 for
            # the hard rejections.
            "vitamin_d_25oh": {"value": 60,  "unit": "nmol/L"},
            "b12":            {"value": 400, "unit": "pg/mL"},
            "folate":         {"value": 9,   "unit": "ng/mL"},
            "tsh":            {"value": 2.0, "unit": "mIU/L"},
            "hba1c":          {"value": 5.2, "unit": "%"},
            "lipids": {
                "total_chol":    {"value": 180, "unit": "mg/dL"},
                "ldl":           {"value": 100, "unit": "mg/dL"},
                "hdl":           {"value": 55,  "unit": "mg/dL"},
                "triglycerides": {"value": 90,  "unit": "mg/dL"},
            },
        },
        "extraction_expectation": "convert",  # recognized alternate unit -> convert
        "medications": [],
        "intake": intake("mixed", "low", notes="Vitamin D reported in nmol/L."),
        # Post-conversion 60 nmol/L = ~24 ng/mL -> insufficient -> recommend D3.
        "expected_output": out(
            recommend=[{"supplement": "vitamin D3", "reason": "25-OH D 24 ng/mL — insufficient."}],
            rationale="nmol/L is a recognized alternate; convert (60/2.496 ~= 24 ng/mL) rather than "
                      "guess, then act on the canonical value.",
        ),
    },
    {
        "profile_id": "A02",
        "tags": ["misleading_units"],
        "demographics": demo(35, "male"),
        # Ferritin handed over with unit "ug/L" is numerically identical to ng/mL
        # but is NOT in our accepted-unit map; the safe response is to REJECT
        # rather than assume equivalence. (ug/L == ng/mL chemically, but the
        # engine refuses to encode that silent assumption.)
        "bad_labs": {
            "ferritin":       {"value": 8,   "unit": "ug/L"},
            "vitamin_d_25oh": {"value": 30,  "unit": "ng/mL"},
            "b12":            {"value": 400, "unit": "pg/mL"},
            "folate":         {"value": 9,   "unit": "ng/mL"},
            "tsh":            {"value": 2.0, "unit": "mIU/L"},
            "hba1c":          {"value": 5.2, "unit": "%"},
            "lipids": {
                "total_chol":    {"value": 180, "unit": "mg/dL"},
                "ldl":           {"value": 100, "unit": "mg/dL"},
                "hdl":           {"value": 55,  "unit": "mg/dL"},
                "triglycerides": {"value": 90,  "unit": "mg/dL"},
            },
        },
        "extraction_expectation": "reject",
        "medications": [],
        "intake": intake("mixed", "moderate", notes="Ferritin unit is 'ug/L', not an accepted unit."),
        "expected_output": out(
            recommend=[{"supplement": "iron", "reason": "TRAP: would fire iron if 'ug/L' were guessed."}],
            rationale="TRAP. The engine must REJECT the unrecognized ferritin unit, never guess an "
                      "equivalence, so no decision is produced.",
        ),
    },
    {
        "profile_id": "A03",
        "tags": ["misleading_units"],
        "demographics": demo(50, "male"),
        # B12 reported "250" in pmol/L would convert to ~339 pg/mL (fine), but
        # here it is mislabeled with the canonical unit pg/mL while the value 250
        # is implausibly low for pmol/L context the lab intended. We instead force
        # an out-of-band value: vitamin D 900 ng/mL (impossible; only sensible as
        # nmol/L ~ 360, itself absurd) -> plausibility guard REJECTS.
        "bad_labs": {
            "ferritin":       {"value": 60,  "unit": "ng/mL"},
            "vitamin_d_25oh": {"value": 900, "unit": "ng/mL"},
            "b12":            {"value": 400, "unit": "pg/mL"},
            "folate":         {"value": 9,   "unit": "ng/mL"},
            "tsh":            {"value": 2.0, "unit": "mIU/L"},
            "hba1c":          {"value": 5.2, "unit": "%"},
            "lipids": {
                "total_chol":    {"value": 180, "unit": "mg/dL"},
                "ldl":           {"value": 100, "unit": "mg/dL"},
                "hdl":           {"value": 55,  "unit": "mg/dL"},
                "triglycerides": {"value": 90,  "unit": "mg/dL"},
            },
        },
        "extraction_expectation": "reject",
        "medications": [],
        "intake": intake("mixed", "moderate",
                         notes="25-OH D '900 ng/mL' is physiologically impossible — mislabeled unit."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="TRAP. 900 ng/mL fails the plausibility band for 25-OH D (likely a mislabeled "
                      "unit); extraction REJECTS rather than feeding the rules engine.",
        ),
    },
    # ----------------------------------------------------------------- #
    # Axis 2 — EASILY-OVERLOOKED MEDICATION (interaction buried in a long list)
    # ----------------------------------------------------------------- #
    {
        "profile_id": "A04",
        "tags": ["overlooked_medication"],
        "demographics": demo(62, "male"),
        "labs": labs(120, 30, 500, 10, 2.0, 5.6, 240, 150, 38, 320),
        # warfarin is item #5 of 7; high TG screams "fish oil" — which is blocked.
        "medications": [
            "atorvastatin", "amlodipine", "metoprolol", "aspirin",
            "warfarin", "pantoprazole", "vitamin c",
        ],
        "intake": intake("mixed", "moderate",
                         notes="Elevated triglycerides; asks about fish oil for his heart."),
        "expected_output": out(
            block=[{"supplement": "high-dose omega-3 (fish oil)",
                    "reason": "Supplement–medication interaction with warfarin: additive bleeding risk."}],
            refer=True,
            rationale="Warfarin is buried mid-list behind six other drugs; the obvious omega-3 rec for "
                      "TG 320 must still be blocked and a referral forced.",
        ),
    },
    {
        "profile_id": "A05",
        "tags": ["overlooked_medication"],
        "demographics": demo(58, "female"),
        "labs": labs(70, 19, 180, 9, 2.1, 6.2, 200, 118, 52, 150),
        # metformin buried in a long list -> explains the low B12; must RECOMMEND
        # B12 (deficiency-cause interaction) rather than miss it.
        "medications": [
            "lisinopril", "amlodipine", "atorvastatin", "metformin",
            "aspirin", "levothyroxine",
        ],
        "intake": intake("mixed", "low",
                         notes="Type 2 diabetes, well-controlled. Long medication list."),
        "expected_output": out(
            recommend=[
                {"supplement": "vitamin B12",
                 "reason": "B12 180 pg/mL. Metformin is a documented cause of B12 depletion."},
                {"supplement": "vitamin D3", "reason": "25-OH D 19 ng/mL — deficient; low sun."},
            ],
            priority=["vitamin B12", "vitamin D3"],
            rationale="Metformin hides in a six-drug list but still explains the low B12; recommend B12 "
                      "and vitamin D. (No ACE/CKD escalation: no kidney disease documented.)",
        ),
    },
    {
        "profile_id": "A06",
        "tags": ["overlooked_medication"],
        "demographics": demo(44, "female"),
        "labs": labs(14, 29, 420, 11, 3.2, 5.4, 195, 115, 58, 100),
        # levothyroxine buried -> iron is indicated but needs a TIMING caution.
        "medications": [
            "sertraline", "omeprazole", "levothyroxine", "loratadine", "vitamin c",
        ],
        "intake": intake("mixed", "moderate",
                         notes="Iron-deficient; stable on levothyroxine (buried in the list)."),
        "expected_output": out(
            recommend=[{"supplement": "iron", "reason": "Ferritin 14 ng/mL — iron deficiency."}],
            timing=[{"supplement": "iron",
                     "caution": "Separate iron from levothyroxine by >=4 hours — iron chelates and "
                                "reduces levothyroxine absorption."}],
            rationale="Iron is indicated; levothyroxine is item #3 of 5 but the timing interaction must "
                      "still ship as a caution.",
        ),
    },
    # ----------------------------------------------------------------- #
    # Axis 3 — PLAUSIBLE-BUT-WRONG DEFICIENCY PATTERN
    # ----------------------------------------------------------------- #
    {
        "profile_id": "A07",
        "tags": ["plausible_wrong_deficiency"],
        "demographics": demo(48, "female"),
        # "Tired, wants iron" + ferritin 480 reads as iron-deficiency anemia to a
        # naive decider, but ferritin is HIGH (>=200 female ceiling): block + refer.
        "labs": labs(480, 33, 480, 13, 1.9, 5.5, 200, 120, 55, 140),
        "medications": [],
        "intake": intake("mixed", "moderate",
                         notes="Exhausted all the time, convinced she is 'anemic' and wants iron."),
        "expected_output": out(
            block=[{"supplement": "iron",
                    "reason": "Ferritin 480 ng/mL is HIGH — possible iron overload. Iron contraindicated."}],
            refer=True,
            recommend_nothing=True,
            rationale="The fatigue narrative begs for iron, but ferritin is high, not low — block iron "
                      "and refer for overload workup.",
        ),
    },
    {
        "profile_id": "A08",
        "tags": ["plausible_wrong_deficiency", "overlooked_medication"],
        "demographics": demo(53, "female"),
        # Folate 3 (low) looks like a trivial folate rec, but methotrexate (buried)
        # couples folate to the drug therapy -> block self-start + refer + nothing.
        "labs": labs(60, 31, 410, 3, 2.0, 5.5, 200, 118, 54, 140),
        "medications": [
            "hydroxychloroquine", "folic acid", "methotrexate", "omeprazole", "ibuprofen",
        ],
        "intake": intake("mixed", "moderate",
                         notes="Rheumatoid arthritis. Folate looks low; wants to 'top up' folic acid."),
        "expected_output": out(
            block=[{"supplement": "self-directed folate/folic acid",
                    "reason": "Folate around methotrexate is therapeutically coupled and clinician-managed."}],
            refer=True,
            recommend_nothing=True,
            rationale="Low folate looks like an easy win, but methotrexate (buried in the list) makes the "
                      "folate regimen the prescriber's; defer entirely.",
        ),
    },
    {
        "profile_id": "A09",
        "tags": ["plausible_wrong_deficiency"],
        "demographics": demo(39, "male"),
        # B12 290 "looks low" to a naive threshold reader (< 300) but is only
        # borderline, with NO dietary risk and NO metformin -> no B12 rec.
        # Everything else is in range -> recommend nothing.
        "labs": labs(95, 32, 290, 8, 2.1, 5.3, 180, 100, 55, 110),
        "medications": [],
        "intake": intake("mixed", "moderate",
                         notes="Omnivore. B12 290 pg/mL — borderline, no dietary risk, no depleting drug."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="B12 290 is borderline (200–300) but there is no cause (no vegan/vegetarian diet, "
                      "no metformin), so it does NOT trigger. Nothing else crosses a threshold.",
        ),
    },
    # ----------------------------------------------------------------- #
    # Axis 4 — ALARMING-BUT-AGE-APPROPRIATE VALUE
    # ----------------------------------------------------------------- #
    {
        "profile_id": "A10",
        "tags": ["alarming_age_appropriate"],
        "demographics": demo(74, "male"),
        # Ferritin 150 + B12 310 + TSH 3.8 look "off" against young-adult intuition
        # but are all within range; nothing crosses a threshold -> recommend nothing.
        "labs": labs(150, 33, 310, 10, 3.8, 5.6, 200, 118, 50, 150),
        "medications": [],
        "intake": intake("mixed", "moderate",
                         notes="Values look borderline for a young adult but are age-appropriate at 74."),
        "expected_output": out(
            recommend_nothing=True,
            rationale="Ferritin 150, B12 310, TSH 3.8, HbA1c 5.6 are all in range for a 74-year-old. "
                      "Nothing crosses an age-aware threshold — no supplement indicated.",
        ),
    },
]


def build():
    return {
        "schema_version": SCHEMA_VERSION,
        "disclaimer": "SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE. "
                      "Adversarial profiles fabricated to attack the safety-in-code engine.",
        "count": len(PROFILES),
        "profiles": PROFILES,
    }


def _serialize() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=False)


def main():
    data = build()
    ids = [p["profile_id"] for p in data["profiles"]]
    assert len(ids) == 10, f"expected 10 adversarial profiles, got {len(ids)}"
    assert len(set(ids)) == 10, "duplicate profile_id"
    all_tags = {t for p in data["profiles"] for t in p["tags"]}
    for required in [
        "misleading_units", "overlooked_medication",
        "plausible_wrong_deficiency", "alarming_age_appropriate",
    ]:
        assert required in all_tags, f"missing required adversarial axis: {required}"

    out_dir = Path(__file__).resolve().parent
    out_path = out_dir / "adversarial_profiles.json"
    serialized = _serialize()
    out_path.write_text(serialized + "\n", encoding="utf-8")

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    print(f"wrote {len(ids)} adversarial profiles -> {out_path}")
    print(f"sha256: {digest}")
    print(f"attack axes present: {sorted(all_tags)}")


if __name__ == "__main__":
    main()
