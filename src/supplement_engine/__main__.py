"""CLI for the supplement reasoning engine.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Subcommands:

* ``python -m supplement_engine <profile_id>``          — print the raw decision.
* ``python -m supplement_engine run <profile_id>``      — evaluate + retrieve +
  guard a profile, log the run to SQLite, and print the run_id + guarded output.
* ``python -m supplement_engine replay <run_id>``       — reconstruct and print a
  past case entirely offline from SQLite.
* ``python -m supplement_engine eval``                  — run the full eval harness
  over base + adversarial, write eval_reports/, and log each case run to SQLite.
* ``python -m supplement_engine ablation``              — run the rules-disabled
  naive baseline and write the ablation summary report.

Deterministic throughout. No LLM, no network.
"""

from __future__ import annotations

import json
import sys

from .eval.ablation import run_ablation
from .eval.ablation import write_reports as write_ablation_reports
from .eval.cases import adversarial_cases, base_cases
from .eval.harness import run_eval
from .eval.harness import write_reports as write_eval_reports
from .loader import load_profile, raw_profiles
from .logging_store import connect, load_run, record_run
from .models import Profile
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
    print("  python -m supplement_engine eval                run the eval harness + write reports")
    print("  python -m supplement_engine ablation            run the rules-disabled ablation")
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


def _cmd_eval(db_path: str | None, *, no_adversarial: bool = False) -> int:
    include_adversarial = not no_adversarial
    report = run_eval(include_adversarial=include_adversarial)
    md_path, json_path = write_eval_reports(report)

    # Log each case run to the SQLite store (base + converted adversarial profiles
    # that yield a typed profile). Rejected adversarial cases have no decision.
    conn = connect(db_path) if db_path else connect()
    logged = 0
    try:
        cases = base_cases() + (adversarial_cases() if include_adversarial else [])
        for case in cases:
            if case.is_extraction_target:
                # Rejected cases produce no decision; skip. Converted cases are
                # logged via their extracted profile.
                if case.extraction_expectation == "reject":
                    continue
                from .eval.cases import questionnaire_from_record
                from .extraction import ExtractionError, extract_profile

                try:
                    profile = extract_profile(
                        case.bad_labs, questionnaire_from_record(case.record)
                    ).profile
                except ExtractionError:
                    continue
            else:
                profile = Profile.model_validate(case.record)
            decision = evaluate(profile)
            result = run_case(profile, decision)
            record_run(
                conn,
                profile_id=profile.profile_id,
                guarded=result.guarded,
                retrieval_results=result.retrieval_results,
            )
            logged += 1
    finally:
        conn.close()

    payload = {
        "banner": _BANNER,
        "reports": {"markdown": str(md_path), "json": str(json_path)},
        "logged_runs": logged,
        "aggregates": report.to_dict()["aggregates"],
    }
    print(json.dumps(payload, indent=2))
    # Non-zero exit if any unsafe output slipped through (CI gate).
    return 0 if report.overall.unsafe_count == 0 else 2


def _cmd_ablation(*, no_adversarial: bool = False) -> int:
    include_adversarial = not no_adversarial
    report = run_ablation(include_adversarial=include_adversarial)
    md_path, json_path = write_ablation_reports(report)
    payload = {
        "banner": _BANNER,
        "reports": {"markdown": str(md_path), "json": str(json_path)},
        "summary": report.to_dict()["summary"],
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

    no_adversarial = False
    if "--no-adversarial" in argv:
        no_adversarial = True
        argv.remove("--no-adversarial")

    cmd = argv[0]
    if cmd == "eval":
        return _cmd_eval(db_path, no_adversarial=no_adversarial)
    if cmd == "ablation":
        return _cmd_ablation(no_adversarial=no_adversarial)
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
