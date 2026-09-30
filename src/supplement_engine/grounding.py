"""
Stage 5 — Grounding guard.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Every claim and number that ships must trace to a rule hit or a cited passage.
Anything that doesn't is **dropped**, and each drop is **logged with its
reason**. This is the last line of the safety-in-code posture: even if a later
generation stage hallucinates, an ungrounded claim cannot leave this guard.

Generation is not built yet, so the guard operates over *structured* claims
(:class:`Claim`) that each reference either a ``rule_id`` (from an
:class:`EngineDecision`'s rule hits) or a ``chunk_id`` (from retrieved passages).
:func:`claims_from_decision` derives one grounded claim per rule hit so the guard
can be exercised end-to-end today; :func:`guard_claims` does the verification.

Fully deterministic. No LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models import EngineDecision
from .retrieval import RetrievedChunk

logger = logging.getLogger("supplement_engine.grounding")


@dataclass(frozen=True)
class Claim:
    """A structured statement awaiting verification.

    A claim is grounded iff at least one of ``rule_id`` / ``chunk_id`` resolves
    to a real rule hit in the decision or a real retrieved passage.
    """

    text: str
    rule_id: str | None = None
    chunk_id: str | None = None


@dataclass(frozen=True)
class DroppedClaim:
    """A claim the guard removed, with the reason it failed to ground."""

    text: str
    reason: str


@dataclass
class GuardedDecision:
    """Result of the grounding guard: what shipped and what was dropped."""

    decision: EngineDecision
    kept_claims: list[Claim] = field(default_factory=list)
    dropped_claims: list[DroppedClaim] = field(default_factory=list)


def claims_from_decision(decision: EngineDecision) -> list[Claim]:
    """Derive one structured, rule-backed :class:`Claim` per rule hit.

    Since generation isn't built yet, this is the bridge that lets the guard run
    over real engine output: each rule hit becomes a claim referencing its
    ``rule_id`` (which the guard will find and therefore keep).
    """
    claims: list[Claim] = []
    for hit in decision.rule_hits:
        claims.append(
            Claim(
                text=f"[{hit.action.value}] {hit.subject}: {hit.reason}",
                rule_id=hit.rule_id,
            )
        )
    return claims


def guard_claims(
    decision: EngineDecision,
    claims: list[Claim],
    passages: list[RetrievedChunk],
) -> GuardedDecision:
    """Verify each claim traces to a rule hit or a cited passage.

    A claim is kept iff its ``rule_id`` matches a rule hit in ``decision`` or its
    ``chunk_id`` matches one of the retrieved ``passages``. Otherwise it is
    dropped and the drop is logged with a specific reason.
    """
    valid_rule_ids = {hit.rule_id for hit in decision.rule_hits}
    valid_chunk_ids = {p.chunk_id for p in passages}

    kept: list[Claim] = []
    dropped: list[DroppedClaim] = []

    for claim in claims:
        rule_ok = claim.rule_id is not None and claim.rule_id in valid_rule_ids
        chunk_ok = claim.chunk_id is not None and claim.chunk_id in valid_chunk_ids

        if rule_ok or chunk_ok:
            kept.append(claim)
            continue

        reason = _drop_reason(claim, valid_rule_ids, valid_chunk_ids)
        dropped.append(DroppedClaim(text=claim.text, reason=reason))
        logger.warning("Dropped ungrounded claim %r: %s", claim.text, reason)

    return GuardedDecision(decision=decision, kept_claims=kept, dropped_claims=dropped)


def _drop_reason(
    claim: Claim,
    valid_rule_ids: set[str],
    valid_chunk_ids: set[str],
) -> str:
    if claim.rule_id is None and claim.chunk_id is None:
        return "no citation: claim references neither a rule hit nor a passage."
    parts: list[str] = []
    if claim.rule_id is not None and claim.rule_id not in valid_rule_ids:
        parts.append(f"rule_id {claim.rule_id!r} not among fired rule hits")
    if claim.chunk_id is not None and claim.chunk_id not in valid_chunk_ids:
        parts.append(f"chunk_id {claim.chunk_id!r} not among retrieved passages")
    return "unresolved citation: " + "; ".join(parts) + "."
