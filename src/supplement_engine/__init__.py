"""supplement_engine — Phase 2 deterministic rules engine.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

from .models import (
    Action,
    Block,
    Demographics,
    EngineDecision,
    Intake,
    LabPanel,
    LabValue,
    Lipids,
    Profile,
    Recommendation,
    RuleHit,
    TimingCaution,
)
from .extraction import (
    ExtractionError,
    ExtractionResult,
    UnitConversion,
    assert_expected_units,
    extract_profile,
)
from .grounding import (
    Claim,
    DroppedClaim,
    GuardedDecision,
    claims_from_decision,
    guard_claims,
)
from .pipeline import CaseResult, run_case
from .retrieval import Passage, RetrievedChunk, load_corpus, retrieve
from .rules import canonical, evaluate

__all__ = [
    "evaluate",
    "canonical",
    # extraction
    "extract_profile",
    "assert_expected_units",
    "ExtractionResult",
    "ExtractionError",
    "UnitConversion",
    # retrieval
    "retrieve",
    "load_corpus",
    "Passage",
    "RetrievedChunk",
    # grounding
    "guard_claims",
    "claims_from_decision",
    "Claim",
    "DroppedClaim",
    "GuardedDecision",
    # pipeline
    "run_case",
    "CaseResult",
    "Profile",
    "EngineDecision",
    "Recommendation",
    "Block",
    "TimingCaution",
    "RuleHit",
    "Action",
    "LabValue",
    "Lipids",
    "LabPanel",
    "Demographics",
    "Intake",
]
