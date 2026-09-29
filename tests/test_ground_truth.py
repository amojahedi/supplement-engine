"""Ground-truth acceptance tests: the engine must reproduce the hand-authored
structured decision for all 30 Phase 1 profiles.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

We match on STRUCTURED fields (sets of recommends/blocks, priority order, the
refer / recommend_nothing flags, and presence of timing cautions), never on the
free-text rationale. Supplement names are canonicalized so "vitamin D3",
"vitamin D3 (standard dose)" and "vitamin D" all compare equal.

The unsafe-output rate on this set must be zero: every case is asserted green.
"""

from __future__ import annotations

import pytest

from supplement_engine.loader import raw_profiles
from supplement_engine.rules import canonical, evaluate

ALL_IDS = [r["profile_id"] for r in raw_profiles()]

# P13 is the single documented deviation from the hand-authored priority list.
# The brief (Phase 2, Step 5) makes "B12 must precede folate" an explicit safety
# property (correcting folate alone can mask a B12 deficiency). P13's authored
# order lists folate before B12, which contradicts that rule. We honor the
# brief's safety intent in the ENGINE and assert the *set* + the safety property
# for P13 instead of the exact authored sequence. See NOTE in the test below.
PRIORITY_SEQUENCE_EXACT_EXCEPTIONS = {"P13"}


def _cset(names) -> set[str]:
    return {canonical(n) for n in names}


def _clist(names) -> list[str]:
    return [canonical(n) for n in names]


@pytest.mark.parametrize("pid", ALL_IDS)
def test_recommend_set(pid, profiles, expected):
    d = evaluate(profiles[pid])
    exp = expected[pid]
    assert _cset(r.supplement for r in d.recommend) == _cset(
        x["supplement"] for x in exp["recommend"]
    ), f"{pid}: recommended set mismatch"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_block_set(pid, profiles, expected):
    d = evaluate(profiles[pid])
    exp = expected[pid]
    assert _cset(b.supplement for b in d.block) == _cset(
        x["supplement"] for x in exp["block"]
    ), f"{pid}: block set mismatch"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_flags(pid, profiles, expected):
    d = evaluate(profiles[pid])
    exp = expected[pid]
    assert d.refer_to_clinician == exp["refer_to_clinician"], f"{pid}: refer flag"
    assert d.recommend_nothing == exp["recommend_nothing"], f"{pid}: recommend_nothing flag"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_timing_presence(pid, profiles, expected):
    d = evaluate(profiles[pid])
    exp = expected[pid]
    assert bool(d.timing_cautions) == bool(exp["timing_cautions"]), f"{pid}: timing presence"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_priority_order(pid, profiles, expected):
    d = evaluate(profiles[pid])
    exp = expected[pid]
    got = _clist(d.priority_order)
    want = _clist(exp["priority_order"])

    # The SET of prioritized items must always match the authored ground truth.
    assert set(got) == set(want), f"{pid}: priority set mismatch got={got} want={want}"

    if pid in PRIORITY_SEQUENCE_EXACT_EXCEPTIONS:
        # NOTE: P13 — authored order is iron, folate, B12, D. The brief mandates
        # B12 before folate as a safety property, so the engine emits
        # iron, B12, folate, D. Assert the safety property instead of the
        # authored sequence here.
        if "vitamin_b12" in got and "folate" in got:
            assert got.index("vitamin_b12") < got.index("folate"), (
                f"{pid}: B12 must precede folate (safety property)"
            )
    else:
        assert got == want, f"{pid}: priority order got={got} want={want}"


@pytest.mark.parametrize("pid", ALL_IDS)
def test_provenance_present(pid, profiles):
    """Every recommend/block/timing item must carry a traceable rule_id."""
    d = evaluate(profiles[pid])
    for item in [*d.recommend, *d.block, *d.timing_cautions]:
        assert item.rule_id, f"{pid}: missing rule_id on {item}"
    # And the ledger must contain a hit for every surfaced action.
    hit_ids = {h.rule_id for h in d.rule_hits}
    for item in [*d.recommend, *d.block, *d.timing_cautions]:
        assert item.rule_id in hit_ids, f"{pid}: {item.rule_id} not in rule_hits ledger"


def test_unsafe_output_rate_is_zero(profiles, expected):
    """Aggregate safety gate: no profile may under-block or drop a required referral."""
    for pid, p in profiles.items():
        d = evaluate(p)
        exp = expected[pid]
        # Every block the ground truth requires must be present (never fewer).
        assert _cset(x["supplement"] for x in exp["block"]).issubset(
            _cset(b.supplement for b in d.block)
        ), f"{pid}: dropped a required block (unsafe)"
        # Never fail to refer when the ground truth requires it.
        if exp["refer_to_clinician"]:
            assert d.refer_to_clinician, f"{pid}: dropped a required referral (unsafe)"
        # Never recommend something the ground truth blocks.
        assert not (_cset(r.supplement for r in d.recommend)
                    & _cset(x["supplement"] for x in exp["block"])), (
            f"{pid}: recommended a blocked supplement (unsafe)"
        )
