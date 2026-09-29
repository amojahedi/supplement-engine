"""Helpers to load the Phase 1 synthetic profiles into typed :class:`Profile` models.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .models import Profile


def _repo_root() -> Path:
    # src/supplement_engine/loader.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[2]


def _import_generator():
    """Import phase1/generate_profiles.py as a module (it is not a package)."""
    path = _repo_root() / "phase1" / "generate_profiles.py"
    spec = importlib.util.spec_from_file_location("phase1_generate_profiles", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def raw_profiles() -> list[dict]:
    """Return the raw Phase 1 profile records (including ``expected_output``)."""
    return _import_generator().PROFILES


def load_profiles() -> list[Profile]:
    """Return the Phase 1 profiles as validated :class:`Profile` models."""
    return [Profile.model_validate(rec) for rec in raw_profiles()]


def load_profile(profile_id: str) -> Profile:
    for rec in raw_profiles():
        if rec["profile_id"] == profile_id:
            return Profile.model_validate(rec)
    raise KeyError(f"no such profile: {profile_id}")


def expected_output(profile_id: str) -> dict:
    for rec in raw_profiles():
        if rec["profile_id"] == profile_id:
            return rec["expected_output"]
    raise KeyError(f"no such profile: {profile_id}")
