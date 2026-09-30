"""
Stage 3 — Retrieval over a local NIH-ODS-style fact-sheet corpus.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.

We cannot fetch the network here, so the corpus lives locally under
``data/ods_factsheets/`` as small, clearly-attributed JSON passages — each one
short enough to verify a single claim against. Every passage carries a
``chunk_id``, ``supplement``, ``source`` (naming the ODS fact sheet), and
``text`` written in neutral, paraphrased summary form.

Retrieval is fully deterministic: a small TF-IDF over the corpus with cosine
similarity, tie-broken by ``chunk_id`` so ordering is stable across runs. No
embeddings API, no external services, no LLM.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _corpus_dir() -> Path:
    # src/supplement_engine/retrieval.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[2] / "data" / "ods_factsheets"


_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stopwords kept intentionally tiny; the corpus is small and domain-specific.
_STOPWORDS = frozenset(
    "a an and are as at be by can for from in is it its of on or the to with".split()
)


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


@dataclass(frozen=True)
class Passage:
    """A single retrievable fact-sheet chunk."""

    chunk_id: str
    supplement: str
    source: str
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A passage returned by :func:`retrieve`, with its similarity score."""

    chunk_id: str
    supplement: str
    source: str
    text: str
    score: float


@lru_cache(maxsize=1)
def load_corpus() -> tuple[Passage, ...]:
    """Load and return every passage from ``data/ods_factsheets/`` (cached).

    Sorted by ``chunk_id`` for a deterministic, stable corpus order.
    """
    passages: list[Passage] = []
    for path in sorted(_corpus_dir().glob("*.json")):
        records = json.loads(path.read_text())
        for rec in records:
            passages.append(
                Passage(
                    chunk_id=rec["chunk_id"],
                    supplement=rec["supplement"],
                    source=rec["source"],
                    text=rec["text"],
                )
            )
    passages.sort(key=lambda p: p.chunk_id)
    return tuple(passages)


@lru_cache(maxsize=1)
def _index() -> tuple[tuple[Passage, ...], dict[str, float], list[dict[str, float]]]:
    """Build a TF-IDF index over the corpus (cached).

    Returns ``(passages, idf, doc_vectors)`` where ``doc_vectors[i]`` is the
    L2-normalized TF-IDF vector (term -> weight) for ``passages[i]``.
    """
    passages = load_corpus()
    n = len(passages)
    doc_tokens = [_tokenize(p.text + " " + p.supplement) for p in passages]

    df: dict[str, int] = {}
    for tokens in doc_tokens:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1
    # Smoothed idf; +1 keeps weights positive even for terms in every doc.
    idf = {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    doc_vectors: list[dict[str, float]] = []
    for tokens in doc_tokens:
        tf: dict[str, int] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0) + 1
        vec = {term: count * idf[term] for term, count in tf.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        doc_vectors.append({term: w / norm for term, w in vec.items()})

    return passages, idf, doc_vectors


def _query_vector(query: str, idf: dict[str, float]) -> dict[str, float]:
    tf: dict[str, int] = {}
    for term in _tokenize(query):
        tf[term] = tf.get(term, 0) + 1
    vec = {term: count * idf.get(term, 0.0) for term, count in tf.items()}
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {term: w / norm for term, w in vec.items()}


def retrieve(query: str, top_k: int = 3) -> list[RetrievedChunk]:
    """Return the top-``k`` corpus chunks for ``query``, most relevant first.

    Deterministic: cosine similarity over TF-IDF, ties broken by ``chunk_id``.
    Chunks with zero overlap (score 0) are omitted.
    """
    if top_k <= 0:
        return []
    passages, idf, doc_vectors = _index()
    qvec = _query_vector(query, idf)

    scored: list[RetrievedChunk] = []
    for passage, dvec in zip(passages, doc_vectors):
        # Cosine similarity; both vectors are L2-normalized already.
        score = sum(w * dvec.get(term, 0.0) for term, w in qvec.items())
        if score > 0.0:
            scored.append(
                RetrievedChunk(
                    chunk_id=passage.chunk_id,
                    supplement=passage.supplement,
                    source=passage.source,
                    text=passage.text,
                    score=score,
                )
            )

    scored.sort(key=lambda c: (-c.score, c.chunk_id))
    return scored[:top_k]
