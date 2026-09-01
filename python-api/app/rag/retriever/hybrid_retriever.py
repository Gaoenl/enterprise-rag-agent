"""向量检索、关键词检索和 RRF 融合的统一入口。"""
import hashlib
import logging
from dataclasses import dataclass

from langchain_core.documents import Document

from app.config import get_settings
from app.rag.retriever.keyword_retriever import KeywordRetriever
from app.rag.retriever.parallel_retrieval import (
    run_parallel_retrieval, RetrievalBranchResult, run_parallel_calls,
)
from app.rag.retriever.pgvector_retriever import PgVectorRetriever
from app.rag.retriever.rrf_fusion import RrfFusion
from app.rag.schemas.retrieval_schema import RetrievalCandidate


logger = logging.getLogger(__name__)


@dataclass
class RetrievalStats:
    """一次混合检索的通道统计，供 Trace 与调试展示。"""

    multi_query_count: int = 0
    vector_merged_count: int = 0
    keyword_count: int = 0
    fused_count: int = 0


class HybridRetriever:
    """并行执行两路检索，然后使用 RRF 融合结果。"""

    def __init__(self) -> None:
        """初始化检索器和融合器。"""
        self._settings = get_settings()
        self._vector_retriever = PgVectorRetriever()
        self._keyword_retriever = KeywordRetriever()
        self._rrf_fusion = RrfFusion(
            rrf_k=self._settings.retrieval_rrf_k,
            vector_weight=self._settings.retrieval_vector_weight,
            keyword_weight=self._settings.retrieval_keyword_weight,
        )

    def retrieve(
        self,
        semantic_query: str,
        keywords: list[str],
        tenant_id: int,
        knowledge_base_id: int,
        alternative_queries: list[str] | None = None,
    ) -> list[Document]:
        """多查询并行召回 → 合并去重 → RRF 融合。"""
        documents, _ = self.retrieve_with_stats(
            semantic_query=semantic_query,
            keywords=keywords,
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            alternative_queries=alternative_queries,
        )
        return documents

    def retrieve_with_stats(
        self,
        semantic_query: str,
        keywords: list[str],
        tenant_id: int,
        knowledge_base_id: int,
        alternative_queries: list[str] | None = None,
    ) -> tuple[list[Document], RetrievalStats]:
        """多查询并行召回 → 合并去重 → RRF 融合，并返回各通道统计。"""
        queries=[semantic_query, *(alternative_queries or [])]
        vector_top_k = (
            self._settings.retrieval_multi_query_top_k
            if len(queries) > 1
            else self._settings.retrieval_vector_top_k
        )
        # 1. 每个查询独立向量检索（并行）。
        vector_calls=[
            lambda q=q:self._vector_retriever.retrieve(
                question=q,
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                top_k=vector_top_k,
            )
            for q in queries
        ]
        vector_results=run_parallel_calls(vector_calls)
        # 2. 关键词检索（一路，用主查询关键词）。
        keyword_result = run_parallel_retrieval(
            vector_call=lambda: [],
            keyword_call=lambda: self._retrieve_by_keywords(
                keywords=keywords,
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
            ),
        )[1]
        # 3. 合并多路向量候选：chunk_id 去重 + 内容哈希去重。
        vector_candidates = self._merge_vector_candidates(
            vector_results
        )
        keyword_candidates = keyword_result.candidates
        vector_error = self._first_vector_error(vector_results)
        keyword_error = keyword_result.error

        # 记录向量检索异常。
        if vector_error is not None:
            self._log_retrieval_error(
                message=(
                    "向量检索失败, tenant_id=%s, "
                    "knowledge_base_id=%s"
                ),
                error=vector_error,
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
            )

        # 记录关键词检索异常。
        if keyword_error is not None:
            self._log_retrieval_error(
                message=(
                    "关键词检索失败, tenant_id=%s, "
                    "knowledge_base_id=%s"
                ),
                error=keyword_error,
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
            )

        # 两路都执行失败时，不能继续生成无依据回答。
        if (
            vector_error is not None
            and keyword_error is not None
        ):
            raise RuntimeError(
                "Vector and keyword retrieval both failed"
            ) from vector_error

        # 关键词检索未启用时，向量检索失败后无法降级。
        if (
            vector_error is not None
            and not self._settings.retrieval_enable_keyword
        ):
            raise RuntimeError(
                "Vector retrieval failed"
            ) from vector_error

        # 没有有效关键词时，向量检索失败也无法降级。
        if vector_error is not None and not keywords:
            raise RuntimeError(
                "Vector retrieval failed and keywords are empty"
            ) from vector_error

        # 一路失败时，RRF 会自动使用另一路已有候选结果。
        fused_candidates = self._rrf_fusion.fuse(
            vector_candidates=vector_candidates,
            keyword_candidates=keyword_candidates,
            final_top_k=self._settings.retrieval_fusion_top_k,
        )

        # 转换为 ContextPacker 和后续 RAG 链路使用的 Document。
        documents = [
            self._to_document(candidate)
            for candidate in fused_candidates
        ]
        stats = RetrievalStats(
            multi_query_count=len(queries),
            vector_merged_count=len(vector_candidates),
            keyword_count=len(keyword_candidates),
            fused_count=len(fused_candidates),
        )
        return documents, stats

    @staticmethod
    def _merge_vector_candidates(
            results: list[RetrievalBranchResult],
    ) -> list[RetrievalCandidate]:
        """多路向量候选合并：按 chunk_id 保留最高分，再按内容哈希去重。"""
        settings = get_settings()
        merged: dict[int, RetrievalCandidate] = {}
        for result in results:
            if result.error is not None:
                continue
            for candidate in result.candidates:
                existing = merged.get(candidate.chunk_id)
                if (
                        existing is None
                        or (candidate.vector_score or 0)
                        > (existing.vector_score or 0)
                ):
                    merged[candidate.chunk_id] = candidate

        candidates = list(merged.values())
        if settings.retrieval_dedup_content_hash:
            candidates = HybridRetriever._dedup_by_content(candidates)
        return candidates

    @staticmethod
    def _dedup_by_content(
            candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        """内容哈希去重：正文相同的 chunk 只保留第一条。"""
        seen: set[str] = set()
        result: list[RetrievalCandidate] = []
        for candidate in candidates:
            key = HybridRetriever._content_key(candidate.content)
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    @staticmethod
    def _content_key(content: str) -> str:
        """规范化空白后计算正文哈希。"""
        normalized = " ".join((content or "").split())
        return hashlib.md5(
            normalized.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _first_vector_error(
            results: list[RetrievalBranchResult],
    ) -> Exception | None:
        """只有所有向量路都失败时才视为向量路失败。"""
        errors = [r.error for r in results if r.error is not None]
        return errors[0] if len(errors) == len(results) else None
    def _retrieve_by_keywords(
        self,
        keywords: list[str],
        tenant_id: int,
        knowledge_base_id: int,
    ) -> list[RetrievalCandidate]:
        """根据配置决定是否执行关键词检索。"""
        if (
            not self._settings.retrieval_enable_keyword
            or not keywords
        ):
            return []

        return self._keyword_retriever.retrieve(
            keywords=keywords,
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            top_k=self._settings.retrieval_keyword_top_k,
        )

    @staticmethod
    def _log_retrieval_error(
        message: str,
        error: Exception,
        tenant_id: int,
        knowledge_base_id: int,
    ) -> None:
        """记录异步线程中产生的完整异常堆栈。"""
        logger.error(
            message,
            tenant_id,
            knowledge_base_id,
            exc_info=(
                type(error),
                error,
                error.__traceback__,
            ),
        )

    @staticmethod
    def _to_document(
        candidate: RetrievalCandidate,
    ) -> Document:
        """将统一候选结果转换为 LangChain Document。"""
        return Document(
            page_content=candidate.content,
            metadata={
                "chunk_id": candidate.chunk_id,
                "document_id": candidate.document_id,
                "knowledge_base_id": (
                    candidate.knowledge_base_id
                ),
                "chunk_index": candidate.chunk_index,
                "document_name": candidate.document_name,
                "score": candidate.fusion_score,
                "fusion_score": candidate.fusion_score,
                "vector_score": candidate.vector_score,
                "keyword_score": candidate.keyword_score,
                "vector_rank": candidate.vector_rank,
                "keyword_rank": candidate.keyword_rank,
                "retrieval_sources": (
                    candidate.retrieval_sources
                ),
                "metadata": candidate.metadata,
            },
        )

    # 公开别名：供 RetrievalDebugService 等外部复用多路合并与错误判定。
    merge_vector_candidates = _merge_vector_candidates
    first_vector_error = _first_vector_error
