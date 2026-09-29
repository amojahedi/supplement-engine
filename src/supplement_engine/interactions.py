"""
Interaction table — the deterministic knowledge base of contraindications,
timing cautions, and deficiency causes.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Three interaction classes are represented as *data*:

* ``supplement-medication`` — e.g. warfarin ↔ high-dose omega-3 / vitamin E /
  vitamin K; SSRI ↔ St John's Wort; statin ↔ St John's Wort; digoxin ↔ St
  John's Wort; levothyroxine ↔ iron (timing); methotrexate ↔ folate;
  thiazide ↔ high-dose calcium; metformin → B12 depletion; ACE inhibitor + CKD
  ↔ potassium.
* ``supplement-supplement`` — B12-before-folate priority/masking.
* ``supplement-condition`` — pregnancy ↔ high-dose retinol (teratogen);
  CKD ↔ magnesium / potassium; high ferritin ↔ iron overload.

Each entry carries a stable ``rule_id``, the human-readable ``reason`` (surfaced
verbatim to downstream phases), the ``action`` it drives, and — for blocks — an
optional ``refer`` flag indicating that firing this interaction should also
force a clinician referral.

The engine (rules.py) consumes these; it does not hard-code interaction facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Action

# Canonical medication name aliases -> normalized key used by the table.
MED_ALIASES: dict[str, str] = {
    "warfarin": "warfarin",
    "sertraline": "ssri",
    "ssri": "ssri",
    "atorvastatin": "statin",
    "statin": "statin",
    "digoxin": "digoxin",
    "levothyroxine": "levothyroxine",
    "methotrexate": "methotrexate",
    "hydrochlorothiazide": "thiazide",
    "hctz": "thiazide",
    "thiazide": "thiazide",
    "metformin": "metformin",
    "lisinopril": "ace_inhibitor",
    "ace inhibitor": "ace_inhibitor",
    "ace_inhibitor": "ace_inhibitor",
}


def normalize_med(med: str) -> str:
    return MED_ALIASES.get(med.strip().lower(), med.strip().lower())


@dataclass(frozen=True)
class Interaction:
    rule_id: str
    kind: str            # supplement-medication | supplement-supplement | supplement-condition
    subject: str         # the supplement the action applies to (as surfaced to the user)
    action: Action
    reason: str
    refer: bool = False  # does firing this block also force a clinician referral?
    tags: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# supplement–medication
# --------------------------------------------------------------------------- #
WARFARIN_OMEGA3 = Interaction(
    rule_id="IX-WARFARIN-OMEGA3",
    kind="supplement-medication",
    subject="high-dose omega-3 (fish oil)",
    action=Action.BLOCK,
    reason=(
        "Supplement–medication interaction with warfarin: additive bleeding risk. "
        "The otherwise-obvious rec for high triglycerides is blocked."
    ),
    refer=True,
)

WARFARIN_VITK = Interaction(
    rule_id="IX-WARFARIN-VITK",
    kind="supplement-medication",
    subject="vitamin K supplement",
    action=Action.BLOCK,
    reason="Antagonizes warfarin — destabilizes INR (supplement–medication interaction).",
)

WARFARIN_VITE = Interaction(
    rule_id="IX-WARFARIN-VITE",
    kind="supplement-medication",
    subject="high-dose vitamin E",
    action=Action.BLOCK,
    reason="Additive bleeding risk with warfarin (supplement–medication interaction).",
)

SSRI_SJW = Interaction(
    rule_id="IX-SSRI-SJW",
    kind="supplement-medication",
    subject="St John's Wort",
    action=Action.BLOCK,
    reason=(
        "Supplement–medication interaction with sertraline (SSRI): serotonin "
        "syndrome risk. Must be stopped."
    ),
    refer=True,
)

STATIN_SJW = Interaction(
    rule_id="IX-STATIN-SJW",
    kind="supplement-medication",
    subject="St John's Wort",
    action=Action.BLOCK,
    reason="Induces metabolism of atorvastatin, reducing its effect (supplement–medication interaction).",
    refer=True,
)

DIGOXIN_SJW = Interaction(
    rule_id="IX-DIGOXIN-SJW",
    kind="supplement-medication",
    subject="St John's Wort",
    action=Action.BLOCK,
    reason=(
        "Reduces digoxin levels (supplement–medication interaction) — risks loss "
        "of therapeutic effect."
    ),
    refer=False,  # stable on digoxin; block the blend, no forced referral
)

LEVO_IRON_TIMING = Interaction(
    rule_id="IX-LEVO-IRON-TIMING",
    kind="supplement-medication",
    subject="iron",
    action=Action.TIMING_CAUTION,
    reason=(
        "Separate iron from levothyroxine by >=4 hours — iron chelates and reduces "
        "levothyroxine absorption (supplement–medication interaction)."
    ),
)

METHOTREXATE_FOLATE = Interaction(
    rule_id="IX-MTX-FOLATE",
    kind="supplement-medication",
    subject="self-directed folate/folic acid",
    action=Action.BLOCK,
    reason=(
        "Folate dosing/timing around methotrexate is therapeutically coupled and "
        "clinician-managed (supplement–medication interaction). Do not self-start."
    ),
    refer=True,
)

THIAZIDE_CALCIUM = Interaction(
    rule_id="IX-THIAZIDE-CALCIUM",
    kind="supplement-medication",
    subject="high-dose calcium",
    action=Action.BLOCK,
    reason=(
        "Thiazide reduces calcium excretion — hypercalcemia risk "
        "(supplement–medication interaction). Hard ceiling applies."
    ),
)

METFORMIN_B12 = Interaction(
    rule_id="IX-METFORMIN-B12",
    kind="supplement-medication",
    subject="vitamin B12",
    action=Action.DEFICIENCY_CAUSE,
    reason=(
        "Metformin is a documented cause of B12 depletion (supplement–medication "
        "interaction working in the deficiency direction)."
    ),
)

ACE_CKD_POTASSIUM = Interaction(
    rule_id="IX-ACE-CKD-POTASSIUM",
    kind="supplement-medication",
    subject="potassium",
    action=Action.BLOCK,
    reason="CKD + ACE inhibitor (lisinopril) → hyperkalemia risk. Hard block.",
    refer=True,
)

# --------------------------------------------------------------------------- #
# supplement–condition
# --------------------------------------------------------------------------- #
PREGNANCY_RETINOL = Interaction(
    rule_id="IX-PREG-RETINOL",
    kind="supplement-condition",
    subject="high-dose vitamin A (retinol)",
    action=Action.BLOCK,
    reason="Teratogenic in pregnancy — supplement–condition contraindication.",
    refer=True,
)

CKD_MAGNESIUM = Interaction(
    rule_id="IX-CKD-MAGNESIUM",
    kind="supplement-condition",
    subject="magnesium",
    action=Action.BLOCK,
    reason="Impaired renal clearance in CKD → accumulation risk.",
    refer=True,
)

HIGH_FERRITIN_IRON = Interaction(
    rule_id="IX-HIGH-FERRITIN-IRON",
    kind="supplement-condition",
    subject="iron",
    action=Action.BLOCK,
    reason=(
        "Ferritin is HIGH — possible iron overload. Iron is contraindicated despite "
        "any fatigue narrative. Hard block."
    ),
    refer=True,
)

# --------------------------------------------------------------------------- #
# supplement–supplement
# --------------------------------------------------------------------------- #
B12_BEFORE_FOLATE = Interaction(
    rule_id="IX-B12-BEFORE-FOLATE",
    kind="supplement-supplement",
    subject="vitamin B12",
    action=Action.TIMING_CAUTION,
    reason=(
        "B12 must be assessed/repleted before folate: correcting folate alone can "
        "mask B12 deficiency and allow neurological damage to progress."
    ),
)


ALL_INTERACTIONS: list[Interaction] = [
    WARFARIN_OMEGA3, WARFARIN_VITK, WARFARIN_VITE,
    SSRI_SJW, STATIN_SJW, DIGOXIN_SJW,
    LEVO_IRON_TIMING, METHOTREXATE_FOLATE, THIAZIDE_CALCIUM,
    METFORMIN_B12, ACE_CKD_POTASSIUM,
    PREGNANCY_RETINOL, CKD_MAGNESIUM, HIGH_FERRITIN_IRON,
    B12_BEFORE_FOLATE,
]
