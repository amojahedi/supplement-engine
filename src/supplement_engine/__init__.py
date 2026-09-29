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
from .rules import canonical, evaluate

__all__ = [
    "evaluate",
    "canonical",
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
