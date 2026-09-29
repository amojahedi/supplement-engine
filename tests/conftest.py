"""Shared fixtures — expose the loaded Phase 1 profiles and their ground truth.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

import pytest

from supplement_engine.loader import load_profiles, raw_profiles


@pytest.fixture(scope="session")
def profiles():
    """All 30 Phase 1 profiles as validated Profile models, keyed by id."""
    return {p.profile_id: p for p in load_profiles()}


@pytest.fixture(scope="session")
def expected():
    """The hand-authored ground-truth expected_output, keyed by profile id."""
    return {r["profile_id"]: r["expected_output"] for r in raw_profiles()}


@pytest.fixture(scope="session")
def profile_ids(profiles):
    return sorted(profiles.keys())
