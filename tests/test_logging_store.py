"""Tests for the SQLite logging store + replay round-trip.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

from supplement_engine.logging_store import connect, load_run, record_run
from supplement_engine.pipeline import run_case
from supplement_engine.rules import evaluate


def _run_and_store(profile, db_path):
    decision = evaluate(profile)
    result = run_case(profile, decision)
    conn = connect(db_path)
    try:
        run_id = record_run(
            conn,
            profile_id=profile.profile_id,
            guarded=result.guarded,
            retrieval_results=result.retrieval_results,
        )
    finally:
        conn.close()
    return run_id, result


def test_round_trip_reproduces_decision(profiles, tmp_path):
    profile = profiles["P01"]
    db = tmp_path / "runs.sqlite3"
    run_id, result = _run_and_store(profile, db)

    conn = connect(db)
    try:
        loaded = load_run(conn, run_id)
    finally:
        conn.close()

    assert loaded.profile_id == "P01"
    # The decision reconstructs byte-for-byte (JSON round-trip).
    assert loaded.decision.model_dump_json() == result.decision.model_dump_json()
    # Rule hits, retrieval, and dropped claims all survive.
    assert len(loaded.rule_hits) == len(result.decision.rule_hits)
    assert [h.rule_id for h in loaded.rule_hits] == [h.rule_id for h in result.decision.rule_hits]
    assert [c.chunk_id for c in loaded.retrieval_results] == [
        c.chunk_id for c in result.retrieval_results
    ]
    assert len(loaded.dropped_claims) == len(result.guarded.dropped_claims)


def test_replay_matches_fresh_evaluation(profiles, tmp_path):
    profile = profiles["P23"]
    db = tmp_path / "runs.sqlite3"
    run_id, _ = _run_and_store(profile, db)

    conn = connect(db)
    try:
        loaded = load_run(conn, run_id)
    finally:
        conn.close()

    fresh = evaluate(profile)
    assert loaded.decision.model_dump_json() == fresh.model_dump_json()


def test_unknown_run_id_raises(tmp_path):
    import pytest

    db = tmp_path / "runs.sqlite3"
    conn = connect(db)
    try:
        with pytest.raises(KeyError):
            load_run(conn, 999)
    finally:
        conn.close()


def test_multiple_runs_get_distinct_ids(profiles, tmp_path):
    db = tmp_path / "runs.sqlite3"
    id1, _ = _run_and_store(profiles["P01"], db)
    id2, _ = _run_and_store(profiles["P02"], db)
    assert id1 != id2

    conn = connect(db)
    try:
        assert load_run(conn, id1).profile_id == "P01"
        assert load_run(conn, id2).profile_id == "P02"
    finally:
        conn.close()
