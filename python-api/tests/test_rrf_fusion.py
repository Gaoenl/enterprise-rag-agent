"""Tests for weighted reciprocal rank fusion."""

import pytest

from app.rag.retriever.rrf_fusion import RrfFusion
from app.rag.schemas.retrieval_schema import RetrievalCandidate


def candidate(chunk_id: int, *, vector_score: float | None = None,
              keyword_score: float | None = None) -> RetrievalCandidate:
    """Build the smallest valid retrieval candidate used by fusion tests."""
    return RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=chunk_id,
        knowledge_base_id=1,
        chunk_index=0,
        content=f"chunk-{chunk_id}",
        vector_score=vector_score,
        keyword_score=keyword_score,
    )


def test_weight_changes_fusion_order() -> None:
    """A larger keyword weight should make the keyword-first chunk win."""
    results = RrfFusion(
        rrf_k=60,
        vector_weight=0.5,
        keyword_weight=1.0,
    ).fuse(
        vector_candidates=[candidate(1), candidate(2)],
        keyword_candidates=[candidate(2), candidate(1)],
        final_top_k=2,
    )

    assert [item.chunk_id for item in results] == [2, 1]
    assert results[0].fusion_score > results[1].fusion_score


def test_zero_weight_excludes_candidates_from_that_retriever() -> None:
    """A disabled retrieval route must not contribute standalone chunks."""
    results = RrfFusion(
        vector_weight=0.0,
        keyword_weight=1.0,
    ).fuse(
        vector_candidates=[candidate(1)],
        keyword_candidates=[candidate(2)],
        final_top_k=10,
    )

    assert [item.chunk_id for item in results] == [2]


def test_both_weights_cannot_be_zero() -> None:
    """At least one retrieval route must participate in fusion."""
    with pytest.raises(ValueError, match="at least one"):
        RrfFusion(vector_weight=0.0, keyword_weight=0.0)
