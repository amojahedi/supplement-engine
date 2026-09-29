"""Tiny CLI: ``python -m supplement_engine <profile_id>`` prints the decision.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

import sys

from .loader import load_profile, raw_profiles
from .rules import evaluate


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        ids = ", ".join(p["profile_id"] for p in raw_profiles())
        print("usage: python -m supplement_engine <profile_id>")
        print(f"available: {ids}")
        return 0

    profile_id = argv[0]
    try:
        profile = load_profile(profile_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1

    decision = evaluate(profile)
    print(decision.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
