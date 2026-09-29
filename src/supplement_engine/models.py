"""
Typed Pydantic v2 models for the supplement reasoning engine.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

These mirror the Phase 1 JSON schema exactly. The single most important
invariant: **every lab value carries both a value AND a unit**. mg/dL vs
nmol/L (and similar) is a ~2.5x silent error, so the unit is mandatory and
never inferred.

Provenance is first-class: every recommend / block / timing item records the
``rule_id`` of the rule that produced it (a :class:`RuleHit`). Downstream phases
(the grounding guard) must be able to trace any shipped claim back to the exact
deterministic rule that justified it.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
class LabValue(BaseModel):
    """A single lab measurement. Unit is mandatory (mg/dL vs nmol/L is a 2.5x error)."""

    model_config = {"extra": "forbid"}

    value: float
    unit: str


class Lipids(BaseModel):
    model_config = {"extra": "forbid"}

    total_chol: LabValue
    ldl: LabValue
    hdl: LabValue
    triglycerides: LabValue


class LabPanel(BaseModel):
    model_config = {"extra": "forbid"}

    ferritin: LabValue
    vitamin_d_25oh: LabValue
    b12: LabValue
    folate: LabValue
    tsh: LabValue
    hba1c: LabValue
    lipids: Lipids

    # Convenience accessors so callers don't reach through ``lipids`` everywhere.
    @property
    def triglycerides(self) -> LabValue:
        return self.lipids.triglycerides

    @property
    def ldl(self) -> LabValue:
        return self.lipids.ldl

    @property
    def hdl(self) -> LabValue:
        return self.lipids.hdl

    def triglycerides_high(self) -> bool:
        # Local import to avoid a circular dependency at module load.
        from .reference_ranges import TG_HIGH

        return self.lipids.triglycerides.value >= TG_HIGH


class Demographics(BaseModel):
    model_config = {"extra": "forbid"}

    age: int
    sex: Literal["male", "female"]
    pregnant: bool = False


class Intake(BaseModel):
    model_config = {"extra": "forbid"}

    diet: str
    sun_exposure: str
    gi_conditions: list[str] = Field(default_factory=list)
    pregnancy_status: str = "not_pregnant"
    notes: str = ""


class Profile(BaseModel):
    model_config = {"extra": "ignore"}  # tolerate tags/expected_output on the raw record

    profile_id: str
    demographics: Demographics
    labs: LabPanel
    medications: list[str] = Field(default_factory=list)
    intake: Intake


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
class Action(str, Enum):
    """What a fired rule causes the engine to do."""

    RECOMMEND = "RECOMMEND"
    BLOCK = "BLOCK"
    TIMING_CAUTION = "TIMING_CAUTION"
    DEFICIENCY_CAUSE = "DEFICIENCY_CAUSE"
    ESCALATE = "ESCALATE"


class RuleHit(BaseModel):
    """Provenance record: the exact rule that fired and why.

    Every recommend / block / timing item in an :class:`EngineDecision` is
    backed by at least one RuleHit so the grounding guard can trace it.
    """

    model_config = {"extra": "forbid"}

    rule_id: str
    action: Action
    subject: str  # supplement name, or the escalation subject
    reason: str


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
class Recommendation(BaseModel):
    model_config = {"extra": "forbid"}

    supplement: str
    reason: str
    rule_id: str


class Block(BaseModel):
    model_config = {"extra": "forbid"}

    supplement: str
    reason: str
    rule_id: str


class TimingCaution(BaseModel):
    model_config = {"extra": "forbid"}

    supplement: str
    caution: str
    rule_id: str


class EngineDecision(BaseModel):
    """Structured decision. Fields match the Phase 1 ``expected_output`` schema,
    with an extra ``rule_hits`` provenance ledger attached."""

    model_config = {"extra": "forbid"}

    recommend: list[Recommendation] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)
    block: list[Block] = Field(default_factory=list)
    timing_cautions: list[TimingCaution] = Field(default_factory=list)
    refer_to_clinician: bool = False
    recommend_nothing: bool = False
    rationale: str = ""

    # Provenance ledger — every fired rule, for downstream tracing.
    rule_hits: list[RuleHit] = Field(default_factory=list)

    def recommended_supplements(self) -> list[str]:
        return [r.supplement for r in self.recommend]

    def blocked_supplements(self) -> list[str]:
        return [b.supplement for b in self.block]
