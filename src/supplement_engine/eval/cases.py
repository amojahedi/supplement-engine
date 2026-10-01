"""
Case loading + a typed-profile -> raw-labs round-trip helper for the eval harness.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

The harness exercises extraction by round-tripping each profile's labs back
through :func:`supplement_engine.extraction.extract_profile`. To do that it
rebuilds a raw-labs + questionnaire dict from the typed/raw profile record and
confirms the canonical units and values are recovered.

The adversarial set (``data/adversarial_profiles.py``) is loaded the same way as
the Phase 1 set, with the extra wrinkle that some adversarial records only carry
a ``bad_labs`` block (deliberately broken units) that extraction must REJECT or
CONVERT rather than evaluate.

Deterministic. No LLM, no network.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..loader import _repo_root  # type: ignore[attr-defined]

_SIMPLE_LAB_KEYS = ("ferritin", "vitamin_d_25oh", "b12", "folate", "tsh", "hba1c")
_LIPID_KEYS = ("total_chol", "ldl", "hdl", "triglycerides")


@dataclass
class Case:
    """One evaluable case: its raw record plus provenance of where it came from."""

    profile_id: str
    record: dict[str, Any]              # raw dict (demographics/labs/medications/intake/expected_output)
    source: str                         # "base" | "adversarial"
    tags: list[str] = field(default_factory=list)
    # Extraction-targeting adversarial cases only:
    extraction_expectation: str | None = None  # "reject" | "convert" | None
    bad_labs: dict[str, Any] | None = None

    @property
    def expected_output(self) -> dict[str, Any]:
        return self.record["expected_output"]

    @property
    def is_extraction_target(self) -> bool:
        return self.bad_labs is not None


def _import_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def base_cases() -> list[Case]:
    """The 30 Phase 1 profiles as :class:`Case` objects (source='base')."""
    from ..loader import raw_profiles

    return [
        Case(
            profile_id=rec["profile_id"],
            record=rec,
            source="base",
            tags=list(rec.get("tags", [])),
        )
        for rec in raw_profiles()
    ]


def adversarial_cases() -> list[Case]:
    """The 10 adversarial profiles as :class:`Case` objects (source='adversarial')."""
    module = _import_module_from_path(
        "adversarial_profiles", _repo_root() / "data" / "adversarial_profiles.py"
    )
    cases: list[Case] = []
    for rec in module.PROFILES:
        cases.append(
            Case(
                profile_id=rec["profile_id"],
                record=rec,
                source="adversarial",
                tags=list(rec.get("tags", [])),
                extraction_expectation=rec.get("extraction_expectation"),
                bad_labs=rec.get("bad_labs"),
            )
        )
    return cases


def questionnaire_from_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Build the extraction questionnaire dict from a raw profile record."""
    demo = rec["demographics"]
    intake = rec["intake"]
    return {
        "profile_id": rec["profile_id"],
        "age": demo["age"],
        "sex": demo["sex"],
        "pregnant": demo.get("pregnant", False),
        "diet": intake["diet"],
        "sun_exposure": intake["sun_exposure"],
        "gi_conditions": list(intake.get("gi_conditions", [])),
        "pregnancy_status": intake.get("pregnancy_status", "not_pregnant"),
        "notes": intake.get("notes", ""),
        "medications": list(rec.get("medications", [])),
    }


def raw_labs_from_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Return the raw-labs dict (value+unit per analyte) from a profile record.

    The Phase 1 record already stores labs in exactly the ``{value, unit}`` shape
    extraction expects, so this is effectively an identity round-trip that proves
    extraction recovers the canonical units and values.
    """
    return rec["labs"]
