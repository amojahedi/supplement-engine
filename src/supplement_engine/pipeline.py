"""
Orchestration — wire the deterministic stages together for one case.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

``run_case`` evaluates a profile (rules engine), retrieves supporting ODS
passages for the supplements the decision touched, derives rule-backed claims,
and runs the grounding guard. No LLM, no network, no agent framework.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grounding import GuardedDecision, claims_from_decision, guard_claims
from .models import EngineDecision, Profile
from .retrieval import RetrievedChunk, retrieve


@dataclass
class CaseResult:
    """Everything produced for one case run (also what gets logged)."""

    profile_id: str
    decision: EngineDecision
    retrieval_results: list[RetrievedChunk]
    guarded: GuardedDecision


def _retrieval_query(decision: EngineDecision) -> str:
    """Build a deterministic retrieval query from the decision's subjects.

    Uses the supplement/subject of every rule hit so retrieval covers whatever
    the engine actually reasoned about (recommendations, blocks, escalations).
    """
    subjects = [hit.subject for hit in decision.rule_hits]
    subjects += [r.supplement for r in decision.recommend]
    subjects += [b.supplement for b in decision.block]
    # Stable, de-duplicated join.
    seen: list[str] = []
    for s in subjects:
        if s not in seen:
            seen.append(s)
    return " ".join(seen)


def run_case(profile: Profile, decision: EngineDecision, *, top_k: int = 3) -> CaseResult:
    """Run retrieval + grounding over an already-evaluated decision."""
    query = _retrieval_query(decision)
    passages = retrieve(query, top_k=top_k) if query.strip() else []
    claims = claims_from_decision(decision)
    guarded = guard_claims(decision, claims, passages)
    return CaseResult(
        profile_id=profile.profile_id,
        decision=decision,
        retrieval_results=passages,
        guarded=guarded,
    )
