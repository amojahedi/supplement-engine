"""Tests for Stage 3 retrieval — relevance and determinism.

SYNTHETIC DATA · RESEARCH PROTOTYPE · NOT MEDICAL ADVICE.
"""

from __future__ import annotations

from supplement_engine.retrieval import load_corpus, retrieve


def test_corpus_loads_and_is_attributed():
    corpus = load_corpus()
    assert len(corpus) >= 9
    for p in corpus:
        assert p.chunk_id and p.supplement and p.source and p.text
        assert "NIH Office of Dietary Supplements" in p.source
        # passages are kept short (verify-a-single-claim sized)
        assert len(p.text.split()) <= 70


def test_relevant_chunk_retrieved_for_iron_query():
    results = retrieve("low ferritin iron deficiency fatigue", top_k=3)
    assert results
    assert results[0].supplement == "iron"
    assert results[0].score > 0


def test_pregnancy_retinol_query_hits_vitamin_a():
    results = retrieve("high-dose vitamin A retinol pregnancy teratogen", top_k=3)
    chunk_ids = [r.chunk_id for r in results]
    assert "vitamin-a-pregnancy-teratogen" in chunk_ids


def test_retrieval_is_deterministic():
    q = "st john's wort digoxin ssri interaction"
    first = retrieve(q, top_k=5)
    second = retrieve(q, top_k=5)
    assert [(r.chunk_id, r.score) for r in first] == [(r.chunk_id, r.score) for r in second]


def test_top_k_limits_results():
    results = retrieve("vitamin", top_k=2)
    assert len(results) <= 2


def test_zero_overlap_query_returns_nothing():
    assert retrieve("zzz qqq xyzzy plugh", top_k=3) == []


def test_scores_sorted_descending():
    results = retrieve("calcium thiazide hypercalcemia upper limit", top_k=5)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
