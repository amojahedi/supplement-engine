"""Unit tests for each interaction class: supplement-medication,
supplement-supplement, and supplement-condition.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

from supplement_engine.interactions import ALL_INTERACTIONS, normalize_med
from supplement_engine.models import Action
from supplement_engine.rules import canonical, evaluate


def _canon(names):
    return [canonical(n) for n in names]


def _block_ids(d):
    return {b.rule_id for b in d.block}


# --------------------------------------------------------------------------- #
# supplement–medication
# --------------------------------------------------------------------------- #
def test_warfarin_blocks_fish_oil(profiles):
    """P02: warfarin ↔ high-dose omega-3 (fish oil)."""
    d = evaluate(profiles["P02"])
    assert "IX-WARFARIN-OMEGA3" in _block_ids(d)
    assert "omega3" in _canon(b.supplement for b in d.block)
    assert d.refer_to_clinician


def test_warfarin_blocks_vitamin_k_and_e(profiles):
    """P17: warfarin ↔ vitamin K and high-dose vitamin E, but vitamin D still OK."""
    d = evaluate(profiles["P17"])
    ids = _block_ids(d)
    assert "IX-WARFARIN-VITK" in ids and "IX-WARFARIN-VITE" in ids
    assert "vitamin_d" in _canon(r.supplement for r in d.recommend)


def test_ssri_blocks_st_johns_wort_and_refers(profiles):
    """P08: sertraline (SSRI) ↔ St John's Wort -> serotonin syndrome risk."""
    d = evaluate(profiles["P08"])
    assert "IX-SSRI-SJW" in _block_ids(d)
    assert d.refer_to_clinician


def test_statin_blocks_st_johns_wort(profiles):
    """P28: atorvastatin ↔ St John's Wort -> induced metabolism."""
    d = evaluate(profiles["P28"])
    assert "IX-STATIN-SJW" in _block_ids(d)
    assert d.refer_to_clinician
    assert "vitamin_d" in _canon(r.supplement for r in d.recommend)


def test_digoxin_blocks_st_johns_wort_no_refer(profiles):
    """P24: digoxin ↔ St John's Wort; blend blocked but no forced referral."""
    d = evaluate(profiles["P24"])
    assert "IX-DIGOXIN-SJW" in _block_ids(d)
    assert not d.refer_to_clinician
    assert "vitamin_d" in _canon(r.supplement for r in d.recommend)


def test_levothyroxine_iron_timing_caution(profiles):
    """P07: levothyroxine ↔ iron is a TIMING caution, not a block."""
    d = evaluate(profiles["P07"])
    assert "iron" in _canon(r.supplement for r in d.recommend)
    assert any(t.rule_id == "IX-LEVO-IRON-TIMING" for t in d.timing_cautions)
    assert "iron" not in _canon(b.supplement for b in d.block)


def test_thiazide_blocks_high_dose_calcium(profiles):
    """P18: hydrochlorothiazide ↔ high-dose calcium; standard-dose D still OK."""
    d = evaluate(profiles["P18"])
    assert "IX-THIAZIDE-CALCIUM" in _block_ids(d)
    assert "vitamin_d" in _canon(r.supplement for r in d.recommend)


def test_metformin_causes_b12_depletion(profiles):
    """P06: metformin → B12 depletion (deficiency-direction interaction)."""
    d = evaluate(profiles["P06"])
    assert "vitamin_b12" in _canon(r.supplement for r in d.recommend)
    b12_rule = next(r.rule_id for r in d.recommend if canonical(r.supplement) == "vitamin_b12")
    assert b12_rule == "IX-METFORMIN-B12"
    assert not d.refer_to_clinician  # managed T2DM, no referral for that alone


def test_ace_ckd_blocks_potassium(profiles):
    """P25: ACE inhibitor + CKD ↔ potassium (hyperkalemia)."""
    d = evaluate(profiles["P25"])
    assert "IX-ACE-CKD-POTASSIUM" in _block_ids(d)


# --------------------------------------------------------------------------- #
# supplement–condition
# --------------------------------------------------------------------------- #
def test_pregnancy_blocks_retinol(profiles):
    """P05 & P16: pregnancy ↔ high-dose retinol (teratogen)."""
    for pid in ("P05", "P16"):
        d = evaluate(profiles[pid])
        assert "IX-PREG-RETINOL" in _block_ids(d), pid
        assert d.refer_to_clinician


def test_ckd_blocks_magnesium(profiles):
    """P25: CKD ↔ magnesium (accumulation)."""
    d = evaluate(profiles["P25"])
    assert "IX-CKD-MAGNESIUM" in _block_ids(d)


def test_high_ferritin_blocks_iron(profiles):
    """P23: high ferritin ↔ iron overload."""
    d = evaluate(profiles["P23"])
    assert "IX-HIGH-FERRITIN-IRON" in _block_ids(d)


# --------------------------------------------------------------------------- #
# supplement–supplement
# --------------------------------------------------------------------------- #
def test_b12_before_folate_masking_recorded(profiles):
    """P21: B12↔folate masking recorded as a rule hit and enforced in ordering."""
    d = evaluate(profiles["P21"])
    assert any(h.rule_id == "IX-B12-BEFORE-FOLATE" for h in d.rule_hits)
    order = _canon(d.priority_order)
    assert order.index("vitamin_b12") < order.index("folate")


# --------------------------------------------------------------------------- #
# Table integrity
# --------------------------------------------------------------------------- #
def test_all_interaction_classes_present():
    kinds = {ix.kind for ix in ALL_INTERACTIONS}
    assert {"supplement-medication", "supplement-supplement", "supplement-condition"} <= kinds


def test_interaction_rule_ids_unique_per_action():
    seen = set()
    for ix in ALL_INTERACTIONS:
        assert isinstance(ix.action, Action)
        key = (ix.rule_id, ix.subject)
        assert key not in seen, f"duplicate {key}"
        seen.add(key)


def test_med_normalization():
    assert normalize_med("Warfarin") == "warfarin"
    assert normalize_med("sertraline") == "ssri"
    assert normalize_med("atorvastatin") == "statin"
    assert normalize_med("HCTZ") == "thiazide"
    assert normalize_med("lisinopril") == "ace_inhibitor"
