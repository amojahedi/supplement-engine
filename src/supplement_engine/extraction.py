"""
Stage 1 — Extraction.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Parse raw lab records + a questionnaire dict into a typed :class:`Profile`.

The cardinal safety property here is **reject rather than guess on units**.
mg/dL vs nmol/L vs ng/mL is a ~2.5x silent error, so:

* Every lab value must carry an explicit, *recognized* unit. A missing, unknown,
  or implausible unit raises :class:`ExtractionError` — a unit is NEVER defaulted
  or inferred.
* Where a lab has an accepted alternate unit (e.g. vitamin D reported in
  nmol/L instead of the canonical ng/mL), the value is converted with a single
  documented factor and the conversion is recorded on the result. Nothing is
  silently coerced.
* :func:`assert_expected_units` is a guard the rules engine can call to prove it
  only ever sees canonical units — it closes the review gap from PR #1.

Everything here is deterministic Python. No LLM, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    Demographics,
    Intake,
    LabPanel,
    LabValue,
    Lipids,
    Profile,
)


class ExtractionError(ValueError):
    """Raised when a lab value cannot be parsed safely (never guess a unit)."""


# --------------------------------------------------------------------------- #
# Canonical units + accepted alternates (with documented conversion factors)
# --------------------------------------------------------------------------- #
# For every extractable analyte we declare exactly one canonical unit (the unit
# the rules engine + reference_ranges.py assume) and, optionally, accepted
# alternate units that we know how to convert *from*. Any unit not in this map
# for a given analyte is a hard rejection — we do not guess.
#
# Conversion factors are written as: canonical_value = alt_value * factor.
# Each factor is documented inline with its molar-mass / definitional basis.
CANONICAL_UNITS: dict[str, str] = {
    "ferritin": "ng/mL",
    "vitamin_d_25oh": "ng/mL",
    "b12": "pg/mL",
    "folate": "ng/mL",
    "tsh": "mIU/L",
    "hba1c": "%",
    # lipids share one canonical unit
    "total_chol": "mg/dL",
    "ldl": "mg/dL",
    "hdl": "mg/dL",
    "triglycerides": "mg/dL",
}


@dataclass(frozen=True)
class _AltUnit:
    """An accepted alternate unit and the factor to reach the canonical unit."""

    unit: str
    factor: float
    note: str


# analyte -> {normalized alternate unit: _AltUnit}
_ALTERNATES: dict[str, dict[str, _AltUnit]] = {
    # 25-OH vitamin D: 1 ng/mL = 2.496 nmol/L, so ng/mL = nmol/L / 2.496.
    "vitamin_d_25oh": {
        "nmol/l": _AltUnit(
            "nmol/L", 1.0 / 2.496,
            "25-OH D: nmol/L -> ng/mL by dividing by 2.496 (MW 400.6 g/mol).",
        ),
    },
    # B12: 1 pg/mL = 0.7378 pmol/L, so pg/mL = pmol/L / 0.7378.
    "b12": {
        "pmol/l": _AltUnit(
            "pmol/L", 1.0 / 0.7378,
            "B12: pmol/L -> pg/mL by dividing by 0.7378 (MW 1355.4 g/mol).",
        ),
    },
    # Folate: 1 ng/mL = 2.266 nmol/L, so ng/mL = nmol/L / 2.266.
    "folate": {
        "nmol/l": _AltUnit(
            "nmol/L", 1.0 / 2.266,
            "Folate: nmol/L -> ng/mL by dividing by 2.266 (MW 441.4 g/mol).",
        ),
    },
    # Lipids: 1 mg/dL cholesterol = 0.02586 mmol/L; triglycerides use 0.01129.
    "total_chol": {
        "mmol/l": _AltUnit("mmol/L", 1.0 / 0.02586, "Cholesterol: mmol/L -> mg/dL / 0.02586."),
    },
    "ldl": {
        "mmol/l": _AltUnit("mmol/L", 1.0 / 0.02586, "Cholesterol: mmol/L -> mg/dL / 0.02586."),
    },
    "hdl": {
        "mmol/l": _AltUnit("mmol/L", 1.0 / 0.02586, "Cholesterol: mmol/L -> mg/dL / 0.02586."),
    },
    "triglycerides": {
        "mmol/l": _AltUnit("mmol/L", 1.0 / 0.01129, "Triglycerides: mmol/L -> mg/dL / 0.01129."),
    },
}


# Plausibility bounds in the CANONICAL unit. A value outside its band signals a
# mislabeled unit (the whole point of the 2.5x-error defense) and is rejected
# rather than fed to the rules engine.
_PLAUSIBLE: dict[str, tuple[float, float]] = {
    "ferritin": (0.1, 5000.0),        # ng/mL
    "vitamin_d_25oh": (1.0, 200.0),   # ng/mL
    "b12": (30.0, 5000.0),            # pg/mL
    "folate": (0.2, 60.0),            # ng/mL
    "tsh": (0.001, 100.0),            # mIU/L
    "hba1c": (2.0, 20.0),             # %
    "total_chol": (30.0, 800.0),      # mg/dL
    "ldl": (10.0, 600.0),             # mg/dL
    "hdl": (5.0, 200.0),              # mg/dL
    "triglycerides": (10.0, 3000.0),  # mg/dL
}

_LIPID_KEYS = ("total_chol", "ldl", "hdl", "triglycerides")
_SIMPLE_LAB_KEYS = ("ferritin", "vitamin_d_25oh", "b12", "folate", "tsh", "hba1c")


@dataclass
class UnitConversion:
    """Record that an alternate unit was converted to the canonical unit."""

    analyte: str
    from_unit: str
    to_unit: str
    original_value: float
    converted_value: float
    note: str


@dataclass
class ExtractionResult:
    """A parsed :class:`Profile` plus the ledger of any unit conversions applied."""

    profile: Profile
    conversions: list[UnitConversion] = field(default_factory=list)


def _norm_unit(unit: Any) -> str:
    if not isinstance(unit, str):
        raise ExtractionError(f"unit must be a string, got {type(unit).__name__!r}")
    return unit.strip().lower()


def _parse_lab(analyte: str, raw: Any) -> tuple[LabValue, UnitConversion | None]:
    """Parse one raw ``{"value": .., "unit": ..}`` into a canonical LabValue.

    Rejects (via :class:`ExtractionError`) any missing/unknown/implausible unit;
    converts a recognized alternate unit and returns a :class:`UnitConversion`.
    """
    if not isinstance(raw, dict):
        raise ExtractionError(f"{analyte}: expected an object with value+unit, got {raw!r}")
    if "value" not in raw:
        raise ExtractionError(f"{analyte}: missing value")
    if "unit" not in raw or raw["unit"] in (None, ""):
        # Never default a unit — this is the whole safety posture.
        raise ExtractionError(f"{analyte}: missing unit — refusing to guess (mg/dL vs nmol/L is ~2.5x)")

    try:
        value = float(raw["value"])
    except (TypeError, ValueError) as exc:
        raise ExtractionError(f"{analyte}: value {raw['value']!r} is not numeric") from exc

    canonical_unit = CANONICAL_UNITS[analyte]
    unit = _norm_unit(raw["unit"])
    conversion: UnitConversion | None = None

    if unit == canonical_unit.lower():
        canonical_value = value
    elif unit in _ALTERNATES.get(analyte, {}):
        alt = _ALTERNATES[analyte][unit]
        canonical_value = value * alt.factor
        conversion = UnitConversion(
            analyte=analyte,
            from_unit=alt.unit,
            to_unit=canonical_unit,
            original_value=value,
            converted_value=canonical_value,
            note=alt.note,
        )
    else:
        accepted = [canonical_unit] + [a.unit for a in _ALTERNATES.get(analyte, {}).values()]
        raise ExtractionError(
            f"{analyte}: unrecognized unit {raw['unit']!r}; "
            f"accepted units are {accepted} — refusing to guess."
        )

    lo, hi = _PLAUSIBLE[analyte]
    if not (lo <= canonical_value <= hi):
        raise ExtractionError(
            f"{analyte}: value {canonical_value:.3g} {canonical_unit} is outside the "
            f"plausible range [{lo}, {hi}] — likely a mislabeled unit; rejecting."
        )

    return LabValue(value=canonical_value, unit=canonical_unit), conversion


def extract_profile(raw_labs: dict[str, Any], questionnaire: dict[str, Any]) -> ExtractionResult:
    """Extract a typed :class:`Profile` from raw lab text/dict + a questionnaire.

    ``raw_labs`` maps each analyte (ferritin, vitamin_d_25oh, b12, folate, tsh,
    hba1c) plus the four lipid analytes to ``{"value": .., "unit": ..}``. Lipids
    may be nested under a ``"lipids"`` key or provided flat.

    ``questionnaire`` provides demographics + intake fields:
    ``profile_id, age, sex, pregnant, diet, sun_exposure, gi_conditions,
    pregnancy_status, notes, medications``.

    Raises :class:`ExtractionError` on any unsafe/ambiguous lab unit.
    """
    conversions: list[UnitConversion] = []

    labs_in = dict(raw_labs)
    lipids_in = labs_in.pop("lipids", None)

    parsed: dict[str, LabValue] = {}
    for key in _SIMPLE_LAB_KEYS:
        if key not in labs_in:
            raise ExtractionError(f"missing lab: {key}")
        lv, conv = _parse_lab(key, labs_in[key])
        parsed[key] = lv
        if conv:
            conversions.append(conv)

    # Reject unexpected analyte keys rather than silently ignoring them:
    # an unknown key is more likely a typo/mislabel than intentional, and
    # silently dropping it could hide a value the caller believed was parsed.
    unexpected = set(labs_in) - set(_SIMPLE_LAB_KEYS)
    if unexpected:
        raise ExtractionError(
            f"unexpected lab key(s): {', '.join(sorted(unexpected))}"
        )

    # Lipids: accept nested or flat.
    lipid_source = lipids_in if isinstance(lipids_in, dict) else labs_in
    lipids_parsed: dict[str, LabValue] = {}
    for key in _LIPID_KEYS:
        if key not in lipid_source:
            raise ExtractionError(f"missing lipid: {key}")
        lv, conv = _parse_lab(key, lipid_source[key])
        lipids_parsed[key] = lv
        if conv:
            conversions.append(conv)

    for required in ("profile_id", "age", "sex"):
        if required not in questionnaire:
            raise ExtractionError(f"questionnaire: missing {required}")

    demographics = Demographics(
        age=questionnaire["age"],
        sex=questionnaire["sex"],
        pregnant=bool(questionnaire.get("pregnant", False)),
    )
    intake = Intake(
        diet=questionnaire.get("diet", "omnivore"),
        sun_exposure=questionnaire.get("sun_exposure", "moderate"),
        gi_conditions=list(questionnaire.get("gi_conditions", [])),
        pregnancy_status=questionnaire.get("pregnancy_status", "not_pregnant"),
        notes=questionnaire.get("notes", ""),
    )

    profile = Profile(
        profile_id=questionnaire["profile_id"],
        demographics=demographics,
        labs=LabPanel(
            ferritin=parsed["ferritin"],
            vitamin_d_25oh=parsed["vitamin_d_25oh"],
            b12=parsed["b12"],
            folate=parsed["folate"],
            tsh=parsed["tsh"],
            hba1c=parsed["hba1c"],
            lipids=Lipids(
                total_chol=lipids_parsed["total_chol"],
                ldl=lipids_parsed["ldl"],
                hdl=lipids_parsed["hdl"],
                triglycerides=lipids_parsed["triglycerides"],
            ),
        ),
        medications=list(questionnaire.get("medications", [])),
        intake=intake,
    )

    # Belt-and-braces: prove we produced canonical units before returning.
    assert_expected_units(profile.labs)
    return ExtractionResult(profile=profile, conversions=conversions)


def assert_expected_units(labs: LabPanel) -> None:
    """Guard: assert every lab in ``labs`` carries its canonical unit.

    The rules engine (rules.py / reference_ranges.py) assumes canonical units for
    every threshold comparison. Calling this before evaluation guarantees a
    mislabeled unit can never reach the safety logic. Raises
    :class:`ExtractionError` on the first mismatch.
    """
    checks: dict[str, LabValue] = {
        "ferritin": labs.ferritin,
        "vitamin_d_25oh": labs.vitamin_d_25oh,
        "b12": labs.b12,
        "folate": labs.folate,
        "tsh": labs.tsh,
        "hba1c": labs.hba1c,
        "total_chol": labs.lipids.total_chol,
        "ldl": labs.lipids.ldl,
        "hdl": labs.lipids.hdl,
        "triglycerides": labs.lipids.triglycerides,
    }
    for analyte, lv in checks.items():
        expected = CANONICAL_UNITS[analyte]
        if lv.unit != expected:
            raise ExtractionError(
                f"assert_expected_units: {analyte} is {lv.unit!r}, expected canonical "
                f"{expected!r}. The rules engine must only see canonical units."
            )
