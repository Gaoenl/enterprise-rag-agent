
"""检索调试业务服务。"""

from time import perf_counter

from fastapi import HTTPException
from langchain_core.documents import Document

from app.config import get_settings
from app.context.context_packer import ContextPacker
from app.factories.chat_model_factory import get_chat_model
from app.retriever.hybrid_retriever import HybridRetriever
from app.retriever.keyword_extractor import KeywordExtractor
from app.retriever.keyword_retriever import KeywordRetriever
from app.retriever.pgvector_retriever import PgVectorRetriever
from app.retriever.rrf_fusion import RrfFusion
from app.rewriter.retrieval_query_rewriter import RetrievalQueryRewriter
from app.schemas.retrieval_debug_schema import (
    PackedContextData,
    RetrievalCandidateData,
    RetrievalDebugData,
    RetrievalDebugRequest,
    RetrievalMode,
    RetrievalTimingData,
)
from app.schemas.retrieval_schema import RetrievalCandidate
from app.schemas.routing_schema import RetrievalQuery
from app.services.rerank_service import RerankService
from app.retriever.parallel_retrieval import run_parallel_retrieval, run_parallel_calls


class RetrievalDebugService:
    """执行完整检索流程，但不调用 LLM 生成答案。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        # 创建统一的本地关键词提取器。
        self._keyword_extractor = KeywordExtractor()
        # 查询重写器和无 Rewrite 链路共用关键词清理规则。
        self._rewriter = RetrievalQueryRewriter(
            get_chat_model(),
            self._keyword_extractor,
        )
        self._vector_retriever = PgVectorRetriever()
        self._keyword_retriever = KeywordRetriever()
        self._rerank_service = RerankService()
        self._context_packer = ContextPacker()

    def debug(
            self,
            request: RetrievalDebugRequest,
    ) -> RetrievalDebugData:
        """执行检索调试流程。"""
        total_started = perf_counter()
        question = request.question.strip()

        if not question:
            raise HTTPException(
                status_code=400,
                detail="question must not be blank",
            )

        # 使用请求参数；未传入时使用服务端默认配置。
        vector_top_k = (
                request.vector_top_k
                or self._settings.retrieval_vector_top_k
        )
        keyword_top_k = (
                request.keyword_top_k
                or self._settings.retrieval_keyword_top_k
        )
        fusion_top_k = (
                request.fusion_top_k
                or self._settings.retrieval_fusion_top_k
        )
        final_top_k = (
                request.final_top_k
                or self._settings.retrieval_final_top_k
        )
        rrf_k = (
                request.rrf_k
                or self._settings.retrieval_rrf_k
        )
        vector_weight = (
            request.vector_weight
            if request.vector_weight is not None
            else self._settings.retrieval_vector_weight
        )
        keyword_weight = (
            request.keyword_weight
            if request.keyword_weight is not None
            else self._settings.retrieval_keyword_weight
        )

        # 权重只影响混合检索；允许关闭一路，但不能同时关闭两路。
        if (
            request.mode == RetrievalMode.HYBRID
            and vector_weight == 0
            and keyword_weight == 0
        ):
            raise HTTPException(
                status_code=400,
                detail="at least one retrieval weight must be positive",
            )

        timings = RetrievalTimingData()
        warnings: list[str] = []
        degraded = False

        if request.knowledge_base_id is None:
            warnings.append(
                "未指定知识库，已在当前租户全部知识库范围内检索；"
                "跨库向量可能由不同模型生成，向量检索结果仅供参考。"
            )

        # 1. 将原始问题转换成语义查询和关键词。
        started = perf_counter()
        retrieval_query = self._rewrite_query(
            question=question,
            enabled=request.enable_rewrite,
        )
        timings.rewrite_millis = self._elapsed_millis(started)
        # 多查询开关：请求允许 && 服务端启用。
        multi_query = (
                request.enable_multi_query
                and self._settings.retrieval_multi_query_enabled
        )
        alternative_queries = (
            retrieval_query.alternative_queries
            if self._settings.retrieval_multi_query_enabled
            else []
        )
        # 合并模型生成的关键词同义变体（去重后用于关键词检索）。
        keywords = RetrievalDebugService._merge_keywords(
            retrieval_query
        )
        # 多查询时每个子查询单独向量召回的数量。
        effective_vector_top_k = (
            self._settings.retrieval_multi_query_top_k
            if len([retrieval_query.semantic_query, *alternative_queries]) > 1
            else vector_top_k
        )
        vector_candidates: list[RetrievalCandidate] = []
        keyword_candidates: list[RetrievalCandidate] = []
        vector_error: Exception | None = None
        keyword_error: Exception | None = None

        if request.mode == RetrievalMode.HYBRID:
            # 多路向量并行（主查询 + 子查询），关键词一路并行。
            queries = [
                retrieval_query.semantic_query,
                *alternative_queries,
            ]
            vector_calls = [
                lambda q=q: self._vector_retriever.retrieve(
                    question=q,
                    tenant_id=request.tenant_id,
                    knowledge_base_id=request.knowledge_base_id,
                    top_k=effective_vector_top_k,
                )
                for q in queries
            ]
            keyword_call = lambda: self._keyword_retriever.retrieve(
                keywords=keywords,
                tenant_id=request.tenant_id,
                knowledge_base_id=request.knowledge_base_id,
                top_k=keyword_top_k,
            )
            vector_results = run_parallel_calls(vector_calls)
            keyword_result = run_parallel_calls([keyword_call])[0]
            # 合并多路向量候选：chunk_id + 内容哈希去重。
            vector_candidates = (
                HybridRetriever._merge_vector_candidates(
                    vector_results
                )
            )
            keyword_candidates = keyword_result.candidates
            vector_error = HybridRetriever._first_vector_error(
                vector_results
            )
            keyword_error = keyword_result.error
            timings.vector_millis = sum(
                result.elapsed_millis
                for result in vector_results
            )
            timings.keyword_millis = (
                keyword_result.elapsed_millis
            )

        elif request.mode == RetrievalMode.VECTOR:
            started = perf_counter()

            try:
                queries = [
                    retrieval_query.semantic_query,
                    *alternative_queries,
                ]
                vector_results = run_parallel_calls(
                    [
                        lambda q=q: self._vector_retriever.retrieve(
                            question=q,
                            tenant_id=request.tenant_id,
                            knowledge_base_id=(
                                request.knowledge_base_id
                            ),
                            top_k=effective_vector_top_k,
                        )
                        for q in queries
                    ]
                )
                vector_candidates = (
                    HybridRetriever.merge_vector_candidates(
                        vector_results
                    )
                )
                vector_error = (
                    HybridRetriever.first_vector_error(
                        vector_results
                    )
                )
            except Exception as exception:
                vector_error = exception
            finally:
                timings.vector_millis = self._elapsed_millis(started)

        else:
            started = perf_counter()

            try:
                keyword_candidates = self._keyword_retriever.retrieve(
                    keywords=keywords,
                    tenant_id=request.tenant_id,
                    knowledge_base_id=request.knowledge_base_id,
                    top_k=keyword_top_k,
                )
            except Exception as exception:
                keyword_error = exception
            finally:
                timings.keyword_millis = self._elapsed_millis(started)

        # 校验检索异常并处理混合检索降级。
        degraded = self._handle_retrieval_errors(
            mode=request.mode,
            vector_error=vector_error,
            keyword_error=keyword_error,
            warnings=warnings,
        )

        # 4. 合并两路检索结果。
        started = perf_counter()

        if request.mode == RetrievalMode.HYBRID:
            fusion_candidates = RrfFusion(
                rrf_k=rrf_k,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
            ).fuse(
                vector_candidates=vector_candidates,
                keyword_candidates=keyword_candidates,
                final_top_k=fusion_top_k,
            )
        elif request.mode == RetrievalMode.VECTOR:
            fusion_candidates = [
                item.model_copy(deep=True)
                for item in vector_candidates[:fusion_top_k]
            ]
        else:
            fusion_candidates = [
                item.model_copy(deep=True)
                for item in keyword_candidates[:fusion_top_k]
            ]

        timings.fusion_millis = self._elapsed_millis(started)

        # 转换成 RerankService 和 ContextPacker 使用的 Document。
        fusion_documents = [
            self._candidate_to_document(candidate)
            for candidate in fusion_candidates
        ]

        # 5. 执行 Rerank；关闭时直接截断融合结果。
        started = perf_counter()
        rerank_applied = False

        if request.enable_rerank and fusion_documents:
            rerank_documents = self._rerank_service.rerank(
                query=question,
                documents=fusion_documents,
            )[:final_top_k]

            # Rerank 成功时会向 metadata 写入 rerank_score。
            rerank_applied = any(
                document.metadata.get("rerank_score")
                is not None
                for document in rerank_documents
            )

            if (
                    self._settings.rerank_enabled
                    and not rerank_applied
            ):
                degraded = True
                warnings.append(
                    "Rerank 执行失败，已降级使用融合结果"
                )

            if not self._settings.rerank_enabled:
                warnings.append(
                    "服务端未启用 Rerank，已使用融合结果"
                )
        else:
            rerank_documents = fusion_documents[:final_top_k]

        timings.rerank_millis = self._elapsed_millis(started)

        # 6. 按字符预算打包最终上下文。
        started = perf_counter()
        packed_context = self._context_packer.pack(
            rerank_documents
        )
        timings.packing_millis = self._elapsed_millis(started)
        timings.total_millis = self._elapsed_millis(total_started)

        return RetrievalDebugData(
            original_query=question,
            semantic_query=retrieval_query.semantic_query,
            keywords=retrieval_query.keywords,
            mode=request.mode,
            rewrite_applied=request.enable_rewrite,
            rerank_applied=rerank_applied,
            degraded=degraded,
            vector_results=[
                self._candidate_to_data(candidate)
                for candidate in vector_candidates
            ],
            keyword_results=[
                self._candidate_to_data(candidate)
                for candidate in keyword_candidates
            ],
            fusion_results=[
                self._candidate_to_data(
                    candidate,
                    fusion_rank=index,
                )
                for index, candidate in enumerate(
                    fusion_candidates,
                    start=1,
                )
            ],
            rerank_results=[
                self._document_to_data(document)
                for document in rerank_documents
            ],
            packed_context=PackedContextData(
                text=packed_context.text,
                total_chars=packed_context.total_chars,
                truncated=packed_context.truncated,
                documents=[
                    self._document_to_data(document)
                    for document in packed_context.documents
                ],
            ),
            timings=timings,
            warnings=warnings,
        )
    def _rewrite_query(
        self,
        question: str,
        enabled: bool,
    ) -> RetrievalQuery:
        """执行模型查询改写，或使用本地规则提取关键词。"""
        if enabled:
            return self._rewriter.rewrite(question)
        # 关闭 Rewrite 时不调用模型，直接使用原问题和本地关键词。
        return RetrievalQuery(
            semantic_query=question,
            keywords=self._keyword_extractor.extract(question),
            alternative_queries=[],
        )

    @staticmethod
    def _handle_retrieval_errors(
        mode: RetrievalMode,
        vector_error: Exception | None,
        keyword_error: Exception | None,
        warnings: list[str],
    ) -> bool:
        """处理单路错误和混合检索降级。"""
        if mode == RetrievalMode.VECTOR and vector_error:
            raise HTTPException(
                status_code=502,
                detail=f"Vector retrieval failed: {vector_error}",
            )

        if mode == RetrievalMode.KEYWORD and keyword_error:
            raise HTTPException(
                status_code=502,
                detail=f"Keyword retrieval failed: {keyword_error}",
            )

        if (
            mode == RetrievalMode.HYBRID
            and vector_error
            and keyword_error
        ):
            raise HTTPException(
                status_code=502,
                detail="Vector and keyword retrieval both failed",
            )

        if vector_error:
            warnings.append(
                "向量检索失败，已降级使用关键词结果"
            )
            return True

        if keyword_error:
            warnings.append(
                "关键词检索失败，已降级使用向量结果"
            )
            return True

        return False

    @staticmethod
    def _merge_keywords(
        retrieval_query: RetrievalQuery,
    ) -> list[str]:
        """合并关键词与同义词变体，去重后返回。"""
        keywords = list(retrieval_query.keywords)
        if retrieval_query.synonym_keywords:
            keywords.extend(retrieval_query.synonym_keywords)

        seen: set[str] = set()
        result: list[str] = []
        for keyword in keywords:
            key = keyword.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(keyword)
        return result

    @staticmethod
    def _candidate_to_document(
        candidate: RetrievalCandidate,
    ) -> Document:
        """将数据库候选结果转换成 LangChain Document。"""
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
                "vector_score": candidate.vector_score,
                "keyword_score": candidate.keyword_score,
                "fusion_score": candidate.fusion_score,
                "vector_rank": candidate.vector_rank,
                "keyword_rank": candidate.keyword_rank,
                "retrieval_sources": (
                    candidate.retrieval_sources
                ),
                "metadata": candidate.metadata,
            },
        )

    @staticmethod
    def _candidate_to_data(
        candidate: RetrievalCandidate,
        fusion_rank: int | None = None,
    ) -> RetrievalCandidateData:
        """将检索候选转换成接口响应。"""
        return RetrievalCandidateData(
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            knowledge_base_id=candidate.knowledge_base_id,
            chunk_index=candidate.chunk_index,
            document_name=candidate.document_name,
            content=candidate.content,
            vector_score=candidate.vector_score,
            keyword_score=candidate.keyword_score,
            fusion_score=candidate.fusion_score,
            vector_rank=candidate.vector_rank,
            keyword_rank=candidate.keyword_rank,
            fusion_rank=fusion_rank,
            retrieval_sources=candidate.retrieval_sources,
            metadata=candidate.metadata,
        )

    @staticmethod
    def _document_to_data(
        document: Document,
    ) -> RetrievalCandidateData:
        """将 Rerank 或 Context 文档转换成响应对象。"""
        metadata = document.metadata

        return RetrievalCandidateData(
            chunk_id=metadata.get("chunk_id"),
            document_id=metadata.get("document_id"),
            knowledge_base_id=metadata.get(
                "knowledge_base_id"
            ),
            chunk_index=metadata.get("chunk_index"),
            document_name=metadata.get("document_name"),
            content=document.page_content,
            vector_score=metadata.get("vector_score"),
            keyword_score=metadata.get("keyword_score"),
            fusion_score=metadata.get("fusion_score"),
            rerank_score=metadata.get("rerank_score"),
            vector_rank=metadata.get("vector_rank"),
            keyword_rank=metadata.get("keyword_rank"),
            rerank_rank=metadata.get("rerank_rank"),
            retrieval_sources=metadata.get(
                "retrieval_sources",
                [],
            ),
            metadata=metadata.get("metadata", {}),
            citation_index=metadata.get("citation_index"),
            context_truncated=metadata.get(
                "context_truncated",
                False,
            ),
        )

    @staticmethod
    def _elapsed_millis(started: float) -> int:
        """计算从 started 到当前时间的毫秒数。"""
        return round(
            (perf_counter() - started) * 1000
        )
