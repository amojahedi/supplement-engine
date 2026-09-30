"""Tests for Stage 5 grounding guard — keep what traces, drop + log what doesn't.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

import logging

from supplement_engine.grounding import (
    Claim,
    claims_from_decision,
    guard_claims,
)
from supplement_engine.models import Action, EngineDecision, RuleHit
from supplement_engine.retrieval import RetrievedChunk


def _decision_with_hit():
    return EngineDecision(
        rule_hits=[
            RuleHit(rule_id="RULE-IRON-LOW", action=Action.RECOMMEND,
                    subject="iron", reason="Ferritin low."),
        ]
    )


def _passage(chunk_id="iron-deficiency-anemia"):
    return RetrievedChunk(
        chunk_id=chunk_id, supplement="iron",
        source="NIH Office of Dietary Supplements — Iron Fact Sheet",
        text="Low ferritin reflects depleted iron stores.", score=0.5,
    )


def test_rule_backed_claim_is_kept():
    decision = _decision_with_hit()
    claims = [Claim(text="Iron is indicated.", rule_id="RULE-IRON-LOW")]
    guarded = guard_claims(decision, claims, passages=[])
    assert len(guarded.kept_claims) == 1
    assert guarded.dropped_claims == []


def test_passage_backed_claim_is_kept():
    decision = _decision_with_hit()
    claims = [Claim(text="Low ferritin means depleted stores.",
                    chunk_id="iron-deficiency-anemia")]
    guarded = guard_claims(decision, claims, passages=[_passage()])
    assert len(guarded.kept_claims) == 1
    assert guarded.dropped_claims == []


def test_ungrounded_claim_is_dropped_and_logged(caplog):
    decision = _decision_with_hit()
    claims = [Claim(text="Take 5000 mg of iron daily.")]  # no citation at all
    with caplog.at_level(logging.WARNING, logger="supplement_engine.grounding"):
        guarded = guard_claims(decision, claims, passages=[_passage()])
    assert guarded.kept_claims == []
    assert len(guarded.dropped_claims) == 1
    dropped = guarded.dropped_claims[0]
    assert dropped.text == "Take 5000 mg of iron daily."
    assert "no citation" in dropped.reason
    # The drop is logged with its reason.
    assert any("Dropped ungrounded claim" in rec.message for rec in caplog.records)


def test_mixed_claims_partition_correctly():
    decision = _decision_with_hit()
    claims = [
        Claim(text="rule-backed", rule_id="RULE-IRON-LOW"),          # kept
        Claim(text="passage-backed", chunk_id="iron-deficiency-anemia"),  # kept
        Claim(text="bogus rule", rule_id="RULE-DOES-NOT-EXIST"),     # dropped
        Claim(text="bogus chunk", chunk_id="not-a-chunk"),           # dropped
        Claim(text="nothing at all"),                                # dropped
    ]
    guarded = guard_claims(decision, claims, passages=[_passage()])
    assert {c.text for c in guarded.kept_claims} == {"rule-backed", "passage-backed"}
    assert {d.text for d in guarded.dropped_claims} == {
        "bogus rule", "bogus chunk", "nothing at all"
    }


def test_unresolved_rule_id_reason_names_the_id():
    decision = _decision_with_hit()
    claims = [Claim(text="x", rule_id="RULE-DOES-NOT-EXIST")]
    guarded = guard_claims(decision, claims, passages=[])
    assert "RULE-DOES-NOT-EXIST" in guarded.dropped_claims[0].reason


def test_claims_from_decision_all_ground(profiles):
    from supplement_engine.rules import evaluate

    decision = evaluate(profiles["P01"])
    claims = claims_from_decision(decision)
    assert len(claims) == len(decision.rule_hits)
    guarded = guard_claims(decision, claims, passages=[])
    # Every derived claim is rule-backed, so nothing drops.
    assert guarded.dropped_claims == []
    assert len(guarded.kept_claims) == len(decision.rule_hits)
