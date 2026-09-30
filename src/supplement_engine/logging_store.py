"""
Phase 3 infrastructure — SQLite logging store.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

Logs, per case run: the ``profile_id``, every rule hit, the retrieval results,
the dropped claims (with reasons), and the final guarded decision (as JSON).
Provides :func:`record_run` to persist a run and :func:`load_run` to reconstruct
it offline — the basis for the ``replay`` CLI. stdlib ``sqlite3`` only; no ORM.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .grounding import DroppedClaim, GuardedDecision
from .models import EngineDecision, RuleHit
from .retrieval import RetrievedChunk

DEFAULT_DB_PATH = Path("supplement_runs.sqlite3")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    decision    TEXT NOT NULL   -- final guarded EngineDecision as JSON
);
CREATE TABLE IF NOT EXISTS rule_hits (
    run_id   INTEGER NOT NULL REFERENCES runs(run_id),
    seq      INTEGER NOT NULL,
    rule_id  TEXT NOT NULL,
    action   TEXT NOT NULL,
    subject  TEXT NOT NULL,
    reason   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retrieval_results (
    run_id      INTEGER NOT NULL REFERENCES runs(run_id),
    seq         INTEGER NOT NULL,
    chunk_id    TEXT NOT NULL,
    supplement  TEXT NOT NULL,
    source      TEXT NOT NULL,
    text        TEXT NOT NULL,
    score       REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dropped_claims (
    run_id  INTEGER NOT NULL REFERENCES runs(run_id),
    seq     INTEGER NOT NULL,
    text    TEXT NOT NULL,
    reason  TEXT NOT NULL
);
"""


@dataclass
class LoadedRun:
    """A run reconstructed from the store."""

    run_id: int
    profile_id: str
    created_at: str
    decision: EngineDecision
    rule_hits: list[RuleHit] = field(default_factory=list)
    retrieval_results: list[RetrievedChunk] = field(default_factory=list)
    dropped_claims: list[DroppedClaim] = field(default_factory=list)


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite store and ensure the schema exists."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def record_run(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    guarded: GuardedDecision,
    retrieval_results: list[RetrievedChunk],
) -> int:
    """Persist one case run and return its ``run_id``.

    Stores the profile id, the final guarded decision (JSON), each rule hit, the
    retrieval results, and each dropped claim with its reason.
    """
    decision = guarded.decision
    created_at = datetime.now(timezone.utc).isoformat()

    cur = conn.execute(
        "INSERT INTO runs (profile_id, created_at, decision) VALUES (?, ?, ?)",
        (profile_id, created_at, decision.model_dump_json()),
    )
    run_id = int(cur.lastrowid)

    conn.executemany(
        "INSERT INTO rule_hits (run_id, seq, rule_id, action, subject, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (run_id, i, h.rule_id, h.action.value, h.subject, h.reason)
            for i, h in enumerate(decision.rule_hits)
        ],
    )
    conn.executemany(
        "INSERT INTO retrieval_results (run_id, seq, chunk_id, supplement, source, text, score) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (run_id, i, c.chunk_id, c.supplement, c.source, c.text, c.score)
            for i, c in enumerate(retrieval_results)
        ],
    )
    conn.executemany(
        "INSERT INTO dropped_claims (run_id, seq, text, reason) VALUES (?, ?, ?, ?)",
        [
            (run_id, i, d.text, d.reason)
            for i, d in enumerate(guarded.dropped_claims)
        ],
    )
    conn.commit()
    return run_id


def load_run(conn: sqlite3.Connection, run_id: int) -> LoadedRun:
    """Reconstruct a previously recorded run from the store.

    Raises :class:`KeyError` if ``run_id`` is unknown.
    """
    row = conn.execute(
        "SELECT run_id, profile_id, created_at, decision FROM runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"no such run_id: {run_id}")

    decision = EngineDecision.model_validate_json(row["decision"])

    hit_rows = conn.execute(
        "SELECT rule_id, action, subject, reason FROM rule_hits "
        "WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    rule_hits = [
        RuleHit(rule_id=r["rule_id"], action=r["action"], subject=r["subject"], reason=r["reason"])
        for r in hit_rows
    ]

    ret_rows = conn.execute(
        "SELECT chunk_id, supplement, source, text, score FROM retrieval_results "
        "WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    retrieval_results = [
        RetrievedChunk(
            chunk_id=r["chunk_id"], supplement=r["supplement"], source=r["source"],
            text=r["text"], score=r["score"],
        )
        for r in ret_rows
    ]

    drop_rows = conn.execute(
        "SELECT text, reason FROM dropped_claims WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    dropped_claims = [DroppedClaim(text=r["text"], reason=r["reason"]) for r in drop_rows]

    return LoadedRun(
        run_id=row["run_id"],
        profile_id=row["profile_id"],
        created_at=row["created_at"],
        decision=decision,
        rule_hits=rule_hits,
        retrieval_results=retrieval_results,
        dropped_claims=dropped_claims,
    )
