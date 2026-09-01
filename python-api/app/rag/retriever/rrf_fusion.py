"""Weighted Reciprocal Rank Fusion for retrieval candidates."""

from app.rag.schemas.retrieval_schema import RetrievalCandidate


class RrfFusion:
    """Fuse vector and keyword rankings with configurable route weights."""

    def __init__(
        self,
        rrf_k: int = 60,
        vector_weight: float = 1.0,
        keyword_weight: float = 1.0,
    ) -> None:
        """Validate and store the smoothing constant and route weights."""
        if rrf_k <= 0:
            raise ValueError("rrf_k must be greater than 0")
        if vector_weight < 0 or keyword_weight < 0:
            raise ValueError("retrieval weights must not be negative")
        if vector_weight == 0 and keyword_weight == 0:
            raise ValueError("at least one retrieval weight must be positive")

        self._rrf_k = rrf_k
        self._vector_weight = vector_weight
        self._keyword_weight = keyword_weight

    def fuse(
        self,
        vector_candidates: list[RetrievalCandidate],
        keyword_candidates: list[RetrievalCandidate],
        final_top_k: int,
    ) -> list[RetrievalCandidate]:
        """Deduplicate by chunk ID and rank candidates by Weighted RRF score."""
        if final_top_k <= 0:
            return []

        merged: dict[int, RetrievalCandidate] = {}

        # A zero weight completely disables contributions from that route.
        if self._vector_weight > 0:
            for rank, candidate in enumerate(vector_candidates, start=1):
                item = candidate.model_copy(deep=True)
                item.vector_rank = rank
                item.fusion_score = self._rrf_score(
                    rank,
                    self._vector_weight,
                )

                if "vector" not in item.retrieval_sources:
                    item.retrieval_sources.append("vector")

                merged[item.chunk_id] = item

        if self._keyword_weight > 0:
            for rank, candidate in enumerate(keyword_candidates, start=1):
                existing = merged.get(candidate.chunk_id)

                if existing is None:
                    item = candidate.model_copy(deep=True)
                    item.keyword_rank = rank
                    item.fusion_score = self._rrf_score(
                        rank,
                        self._keyword_weight,
                    )

                    if "keyword" not in item.retrieval_sources:
                        item.retrieval_sources.append("keyword")

                    merged[item.chunk_id] = item
                    continue

                # A chunk found by both routes receives both contributions.
                existing.keyword_rank = rank
                existing.keyword_score = candidate.keyword_score
                existing.fusion_score += self._rrf_score(
                    rank,
                    self._keyword_weight,
                )

                if "keyword" not in existing.retrieval_sources:
                    existing.retrieval_sources.append("keyword")

        sorted_candidates = sorted(
            merged.values(),
            key=lambda item: (
                item.fusion_score,
                item.keyword_score or 0.0,
                item.vector_score or 0.0,
            ),
            reverse=True,
        )

        return sorted_candidates[:final_top_k]

    def _rrf_score(self, rank: int, weight: float) -> float:
        """Calculate one route's Weighted RRF contribution."""
        return weight / (self._rrf_k + rank)
