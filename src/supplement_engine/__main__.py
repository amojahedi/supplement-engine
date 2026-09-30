"""CLI for the supplement reasoning engine.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Subcommands:

* ``python -m supplement_engine <profile_id>``          — print the raw decision.
* ``python -m supplement_engine run <profile_id>``      — evaluate + retrieve +
  guard a profile, log the run to SQLite, and print the run_id + guarded output.
* ``python -m supplement_engine replay <run_id>``       — reconstruct and print a
  past case entirely offline from SQLite.

Deterministic throughout. No LLM, no network.
"""

from __future__ import annotations

import json
import sys

from .loader import load_profile, raw_profiles
from .logging_store import connect, load_run, record_run
from .pipeline import run_case
from .rules import evaluate

_BANNER = "SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE"


def _usage() -> None:
    ids = ", ".join(p["profile_id"] for p in raw_profiles())
    print(f"# {_BANNER}")
    print("usage:")
    print("  python -m supplement_engine <profile_id>        print the decision")
    print("  python -m supplement_engine run <profile_id>    evaluate+guard+log a case")
    print("  python -m supplement_engine replay <run_id>     replay a logged case")
    print(f"available profiles: {ids}")


def _cmd_print(profile_id: str) -> int:
    try:
        profile = load_profile(profile_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(evaluate(profile).model_dump_json(indent=2))
    return 0


def _cmd_run(profile_id: str, db_path: str | None) -> int:
    try:
        profile = load_profile(profile_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1

    decision = evaluate(profile)
    result = run_case(profile, decision)

    conn = connect(db_path) if db_path else connect()
    try:
        run_id = record_run(
            conn,
            profile_id=profile.profile_id,
            guarded=result.guarded,
            retrieval_results=result.retrieval_results,
        )
    finally:
        conn.close()

    payload = {
        "banner": _BANNER,
        "run_id": run_id,
        "profile_id": profile.profile_id,
        "decision": json.loads(decision.model_dump_json()),
        "retrieval_results": [
            {"chunk_id": c.chunk_id, "source": c.source, "score": round(c.score, 4)}
            for c in result.retrieval_results
        ],
        "kept_claims": [c.text for c in result.guarded.kept_claims],
        "dropped_claims": [
            {"text": d.text, "reason": d.reason} for d in result.guarded.dropped_claims
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_replay(run_id_str: str, db_path: str | None) -> int:
    try:
        run_id = int(run_id_str)
    except ValueError:
        print(f"invalid run_id: {run_id_str!r}", file=sys.stderr)
        return 1

    conn = connect(db_path) if db_path else connect()
    try:
        loaded = load_run(conn, run_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        conn.close()

    payload = {
        "banner": _BANNER,
        "run_id": loaded.run_id,
        "profile_id": loaded.profile_id,
        "created_at": loaded.created_at,
        "decision": json.loads(loaded.decision.model_dump_json()),
        "rule_hits": [
            {"rule_id": h.rule_id, "action": h.action.value, "subject": h.subject}
            for h in loaded.rule_hits
        ],
        "retrieval_results": [
            {"chunk_id": c.chunk_id, "source": c.source, "score": round(c.score, 4)}
            for c in loaded.retrieval_results
        ],
        "dropped_claims": [
            {"text": d.text, "reason": d.reason} for d in loaded.dropped_claims
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _usage()
        return 0

    # Optional --db PATH anywhere in the args.
    db_path: str | None = None
    if "--db" in argv:
        i = argv.index("--db")
        try:
            db_path = argv[i + 1]
        except IndexError:
            print("--db requires a path", file=sys.stderr)
            return 1
        del argv[i : i + 2]

    cmd = argv[0]
    if cmd == "run":
        if len(argv) < 2:
            print("run requires a <profile_id>", file=sys.stderr)
            return 1
        return _cmd_run(argv[1], db_path)
    if cmd == "replay":
        if len(argv) < 2:
            print("replay requires a <run_id>", file=sys.stderr)
            return 1
        return _cmd_replay(argv[1], db_path)

    # Backward-compatible: bare profile id.
    return _cmd_print(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
