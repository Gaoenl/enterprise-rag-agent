"""RagEngine：RAG 核心统一入口。

业务层（聊天、面试、媒体等）通过本类使用全部 RAG 能力，不直接触碰
retriever / rewriter / router 等内部组件。

使用方式：
    engine = RagEngine(settings)
    result = engine.query(RagQuery(question="...", knowledge_base_id=1))

流式场景：
    prepared = engine.prepare(request)
    for delta in engine.generate(request, prepared):
        ...
"""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

from langchain_core.documents import Document

from app.rag.clients.embedding_client import EmbeddingClient
from app.rag.clients.llm_client import LlmClient, LlmStreamChunk
from app.rag.context.context_packer import ContextPacker
from app.rag.llm.chat_model_factory import get_chat_model
from app.rag.postprocess.answer_postprocessor import AnswerPostProcessor
from app.rag.retriever.hybrid_retriever import (
    HybridRetriever,
    RetrievalStats,
)
from app.rag.retriever.keyword_extractor import KeywordExtractor
from app.rag.retriever.rerank import RerankService
from app.rag.rewriter.conversation_query_resolver import (
    ConversationQueryResolver,
)
from app.rag.rewriter.retrieval_query_rewriter import (
    RetrievalQueryRewriter,
)
from app.rag.router.intent_router import IntentRouter
from app.rag.router.knowledge_base_selector import (
    KnowledgeBaseSelector,
)
from app.rag.schemas.context_schema import PackedContext
from app.rag.schemas.query_schema import (
    RagPrepared,
    RagQuery,
    RagResult,
)
from app.rag.schemas.routing_schema import (
    L0Intent,
    ResolvedQuery,
    RetrievalQuery,
    RouteDecision,
)
from app.rag.settings import RagSettings
from app.rag.tools.registry import execute, is_registered
from app.rag.trace.trace_recorder import TraceRecorder
from app.schemas.answer_schema import (
    AnswerPostProcessResult,
    AnswerStatus,
)
from app.schemas.chat_schema import ChatHistoryMessage
from app.schemas.trace_schema import TokenUsage


class RagEngine:
    """RAG 核心统一入口。"""

    def __init__(self, settings: RagSettings | None = None) -> None:
        """初始化全部 RAG 组件。"""
        self._settings = settings or RagSettings.from_env()

        self._chat_model = get_chat_model()
        self._keyword_extractor = KeywordExtractor()
        self._query_resolver = ConversationQueryResolver(
            self._chat_model
        )
        self._query_router = IntentRouter()
        self._knowledge_base_selector = KnowledgeBaseSelector()
        self._retrieval_query_rewriter = RetrievalQueryRewriter(
            self._chat_model,
            self._keyword_extractor,
        )
        self._retriever = HybridRetriever()
        self._rerank_service = RerankService()
        self._context_packer = ContextPacker()
        self._llm_client = LlmClient()
        self._answer_postprocessor = AnswerPostProcessor()
        self._embedding_client = EmbeddingClient()

        # Graph 模式按需创建；锁用于避免并发首请求重复编译图。
        self._workflow: Any | None = None
        self._workflow_lock = Lock()

    # ── 基础能力 ────────────────────────────────
    def embed(
        self,
        texts: list[str],
        model: str | None = None,
        dimension: int | None = None,
    ) -> list[list[float]]:
        """批量生成文本向量。"""
        return self._embedding_client.embed_texts(
            texts, model, dimension
        )

    def rewrite(self, query: str) -> RetrievalQuery:
        """查询改写：语义查询 + 关键词 + 同义词 + 多查询子问题。"""
        return self._retrieval_query_rewriter.rewrite(query)

    def retrieve(
        self,
        query: str,
        knowledge_base_id: int,
        tenant_id: int | None = None,
        keywords: list[str] | None = None,
        final_top_k: int | None = None,
    ) -> list[Document]:
        """混合检索，返回文档列表。"""
        rewritten = self.rewrite(query)
        effective_keywords = keywords or self._merge_keywords(rewritten)
        return self._retriever.retrieve(
            semantic_query=rewritten.semantic_query,
            keywords=effective_keywords,
            tenant_id=tenant_id or 0,
            knowledge_base_id=knowledge_base_id,
            alternative_queries=rewritten.alternative_queries,
        )

    def rerank(
        self,
        query: str,
        documents: list[Document],
    ) -> list[Document]:
        """Cross-Encoder 重排。"""
        return self._rerank_service.rerank(query, documents)

    def route_intent(
        self,
        query: str,
        history: list[ChatHistoryMessage] | None = None,
        preferred_knowledge_base_id: int | None = None,
    ) -> RouteDecision:
        """意图路由：规则短路 + 向量/LLM 双路 + 归一化融合。"""
        return self._query_router.route(
            query=query,
            history=history or [],
            preferred_knowledge_base_id=preferred_knowledge_base_id,
        )

    def select_knowledge_base(
        self,
        tenant_id: int,
        user_id: int,
        query: str,
        domain: str | None = None,
        preferred_knowledge_base_id: int | None = None,
    ) -> Any:
        """选择知识库。"""
        return self._knowledge_base_selector.select(
            tenant_id=tenant_id,
            user_id=user_id,
            preferred_knowledge_base_id=preferred_knowledge_base_id,
            query=query,
            domain=domain,
        )

    def pack_context(
        self,
        documents: list[Document],
    ) -> PackedContext:
        """按预算打包上下文。"""
        return self._context_packer.pack(documents)

    # ── 完整问答 ────────────────────────────────
    def query(
        self,
        request: RagQuery,
        recorder: TraceRecorder | None = None,
    ) -> RagResult:
        """执行完整 RAG 问答（非流式）。"""
        prepared = self.prepare(request, recorder=recorder)

        if prepared.clarification_answer is not None:
            return RagResult(
                answer=prepared.clarification_answer,
                answer_status=AnswerStatus.CLARIFICATION_REQUIRED,
                intent=prepared.intent,
                need_rag=False,
                standalone_query=prepared.standalone_query,
                model=prepared.model,
                knowledge_base_id=prepared.knowledge_base_id,
                route=prepared.route,
                route_reason=prepared.route_reason,
            )

        if prepared.no_evidence:
            if recorder is not None:
                recorder.skip(
                    "LLM_GENERATE",
                    reason="检索无依据，未调用模型。",
                )
            return RagResult(
                answer=self._settings.rag_empty_context_message,
                answer_status=AnswerStatus.NO_EVIDENCE,
                intent=prepared.intent,
                need_rag=prepared.need_rag,
                standalone_query=prepared.standalone_query,
                model=prepared.model,
                knowledge_base_id=prepared.knowledge_base_id,
                route=prepared.route,
                route_reason=prepared.route_reason,
            )

        with self._node(
            "LLM_GENERATE",
            {
                "model": prepared.model,
                "streaming": False,
            },
            recorder=recorder,
        ) as node:
            llm_result = self._llm_client.chat(
                question=prepared.standalone_query,
                model=prepared.model,
                history=prepared.history,
                summary=request.summary,
                context=prepared.context,
                rag_mode=prepared.need_rag,
                tool_result=prepared.tool_result,
            )
            if node is not None:
                node.set_output(
                    {
                        "modelName": llm_result.model,
                        "answerChars": len(llm_result.answer),
                        "inputTokens": (
                            llm_result.token_usage.input_tokens
                        ),
                        "outputTokens": (
                            llm_result.token_usage.output_tokens
                        ),
                        "totalTokens": (
                            llm_result.token_usage.total_tokens
                        ),
                    }
                )

        processed = self.postprocess_answer(
            raw_answer=llm_result.answer,
            prepared=prepared,
            recorder=recorder,
        )
        return RagResult(
            answer=processed.answer,
            answer_status=processed.answer_status,
            intent=prepared.intent,
            need_rag=prepared.need_rag,
            standalone_query=prepared.standalone_query,
            model=prepared.model,
            knowledge_base_id=prepared.knowledge_base_id,
            citations=prepared.citations,
            token_usage=llm_result.token_usage,
            route=prepared.route,
            route_reason=prepared.route_reason,
        )

    def prepare(
        self,
        request: RagQuery,
        recorder: TraceRecorder | None = None,
    ) -> RagPrepared:
        """按配置选择 legacy 或 LangGraph 编排。"""
        if self._settings.rag_orchestrator == "graph":
            # 首次进入 Graph 模式时才导入并编译，legacy 模式不加载 LangGraph。
            with self._workflow_lock:
                if self._workflow is None:
                    from app.rag.workflow.runner import RagWorkflow

                    self._workflow = RagWorkflow.from_engine(self)
            return self._workflow.prepare(request, recorder)

        # 默认路径保持原有实现，便于灰度回滚和结果对比。
        return self._prepare_legacy(request, recorder)

    def _prepare_legacy(
        self,
        request: RagQuery,
        recorder: TraceRecorder | None = None,
    ) -> RagPrepared:
        """执行 LLM 生成前的公共编排（路由/检索/重排/打包）。"""
        model = request.model or self._settings.llm_model
        tool_result = ""

        with self._node(
            "QUERY_RESOLVE",
            {"historyCount": len(request.history)},
            recorder=recorder,
        ) as node:
            resolved_query = self._query_resolver.resolve(
                question=request.question,
                history=request.history,
            )
            if node is not None:
                node.set_output(
                    {
                        "rewritten": resolved_query.rewritten,
                        "standaloneQuery": (
                            resolved_query.standalone_query[:1000]
                        ),
                    }
                )

        with self._node("QUERY_ROUTE", recorder=recorder) as node:
            route = self._resolve_route(request, resolved_query)
            if node is not None:
                node.set_output(
                    {
                        "intent": route.intent.value,
                        "domain": route.domain.value,
                        "needRag": route.need_rag,
                        "confidence": route.confidence,
                        "reason": route.reason,
                        "routerPath": route.router_path,
                        "inheritContext": route.inherit_context,
                        "sourceScores": route.source_scores,
                        "intentConfidence": route.intent_confidence,
                    }
                )

        # TOOL 意图：执行工具，结果作为上下文喂给 LLM。
        if route.intent == L0Intent.TOOL:
            if (
                not request.tool_enabled
                or route.tool is None
                or not is_registered(route.tool.tool)
            ):
                self._skip_retrieval_stage(
                    recorder,
                    "工具未开通，进入澄清流程。",
                )
                if recorder is not None:
                    recorder.skip(
                        "LLM_GENERATE",
                        reason="需要澄清，未调用模型。",
                    )
                return RagPrepared(
                    question=request.question,
                    standalone_query=resolved_query.standalone_query,
                    model=model,
                    history=request.history,
                    intent="CLARIFY",
                    need_rag=False,
                    route=route,
                    route_reason=route.reason,
                    clarification_answer=(
                        "当前请求需要调用工具，但该工具尚未开通，"
                        "请稍后再试或换一种问法。"
                    ),
                )
            with self._node(
                "TOOL_EXECUTE",
                {
                    "tool": route.tool.tool,
                    "input": str(route.tool.tool_input)[:500],
                },
                recorder=recorder,
            ) as node:
                try:
                    tool_result = execute(
                        route.tool.tool,
                        route.tool.tool_input,
                    )
                except Exception as exception:
                    if node is not None:
                        node.set_output(
                            {"error": str(exception)[:500]}
                        )
                    self._skip_retrieval_stage(
                        recorder,
                        "工具执行失败，进入澄清流程。",
                    )
                    if recorder is not None:
                        recorder.skip(
                            "LLM_GENERATE",
                            reason="需要澄清，未调用模型。",
                        )
                    return RagPrepared(
                        question=request.question,
                        standalone_query=resolved_query.standalone_query,
                        model=model,
                        history=request.history,
                        intent="CLARIFY",
                        need_rag=False,
                        route=route,
                        route_reason=route.reason,
                        clarification_answer=(
                            f"工具执行失败：{exception}，"
                            "请稍后再试或换一种问法。"
                        ),
                    )
                if node is not None:
                    node.set_output(
                        {"resultChars": len(tool_result)}
                    )

        # 普通对话直接进入 LLM。
        if not route.need_rag:
            self._skip_retrieval_stage(
                recorder,
                "非 RAG 意图，跳过知识库检索。",
            )
            return RagPrepared(
                question=request.question,
                standalone_query=resolved_query.standalone_query,
                model=model,
                history=request.history,
                intent=route.intent.value,
                need_rag=False,
                route=route,
                route_reason=route.reason,
                tool_result=tool_result,
            )

        with self._node(
            "KNOWLEDGE_BASE_SELECT",
            recorder=recorder,
        ) as node:
            selection = self._knowledge_base_selector.select(
                tenant_id=request.tenant_id or 0,
                user_id=request.user_id or 0,
                preferred_knowledge_base_id=(
                    request.knowledge_base_id
                ),
                query=resolved_query.standalone_query,
                domain=route.domain.value,
            )
            if node is not None:
                node.set_output(
                    {
                        "knowledgeBaseId": (
                            selection.knowledge_base_id
                        ),
                        "selectionType": selection.selection_type,
                        "needClarification": (
                            selection.need_clarification
                        ),
                    }
                )

        if selection.need_clarification:
            self._skip_retrieval_stage(
                recorder,
                "知识库不明确，进入澄清流程。",
            )
            if recorder is not None:
                recorder.skip(
                    "LLM_GENERATE",
                    reason="需要澄清，未调用模型。",
                )
            return RagPrepared(
                question=request.question,
                standalone_query=resolved_query.standalone_query,
                model=model,
                history=request.history,
                intent="CLARIFY",
                need_rag=False,
                route=route,
                route_reason=selection.reason,
                clarification_answer=(
                    self._build_clarification_answer(selection)
                ),
            )

        selected_knowledge_base_id = selection.knowledge_base_id

        with self._node(
            "RETRIEVAL_QUERY_REWRITE",
            recorder=recorder,
        ) as node:
            retrieval_query = (
                self._retrieval_query_rewriter.rewrite(
                    resolved_query.standalone_query
                )
            )
            if node is not None:
                node.set_output(
                    {
                        "semanticQuery": (
                            retrieval_query.semantic_query[:1000]
                        ),
                        "keywords": retrieval_query.keywords,
                    }
                )

        with self._node("HYBRID_RETRIEVE", recorder=recorder) as node:
            keywords = self._merge_keywords(retrieval_query)
            retrieved_documents, retrieval_stats = (
                self._retriever.retrieve_with_stats(
                    semantic_query=retrieval_query.semantic_query,
                    keywords=keywords,
                    tenant_id=request.tenant_id or 0,
                    knowledge_base_id=selected_knowledge_base_id,
                    alternative_queries=(
                        retrieval_query.alternative_queries
                        if self._settings.retrieval_multi_query_enabled
                        else []
                    ),
                )
            )
            candidate_count = len(retrieved_documents)
            if node is not None:
                node.set_output(
                    {
                        "candidateCount": candidate_count,
                        "vectorCount": (
                            retrieval_stats.vector_merged_count
                        ),
                        "keywordCount": (
                            retrieval_stats.keyword_count
                        ),
                        "multiQueryCount": (
                            retrieval_stats.multi_query_count
                        ),
                        "fusedCount": retrieval_stats.fused_count,
                    }
                )

        with self._node("RERANK", recorder=recorder) as node:
            reranked_documents = self._rerank_service.rerank(
                query=resolved_query.standalone_query,
                documents=retrieved_documents,
            )
            rerank_count = len(reranked_documents)
            if node is not None:
                node.set_output(
                    {
                        "inputCount": candidate_count,
                        "resultCount": rerank_count,
                    }
                )

        with self._node("CONTEXT_PACK", recorder=recorder) as node:
            packed_context = self._context_packer.pack(
                reranked_documents
            )
            documents = packed_context.documents
            context = packed_context.text
            citations = self._build_citations(documents)
            context_document_count = len(documents)
            if node is not None:
                node.set_output(
                    {
                        "documentCount": context_document_count,
                        "totalChars": packed_context.total_chars,
                        "truncated": packed_context.truncated,
                    }
                )

        return RagPrepared(
            question=request.question,
            standalone_query=resolved_query.standalone_query,
            model=model,
            history=request.history,
            intent=route.intent.value,
            need_rag=True,
            knowledge_base_id=selected_knowledge_base_id,
            route=route,
            route_reason=route.reason,
            context=context,
            documents=documents,
            citations=citations,
            candidate_count=candidate_count,
            rerank_count=rerank_count,
            context_document_count=context_document_count,
            no_evidence=not context.strip(),
        )

    def generate(
        self,
        request: RagQuery,
        prepared: RagPrepared,
        recorder: TraceRecorder | None = None,
    ) -> Iterator[str]:
        """流式生成回答，产出文本增量。"""
        for chunk in self.generate_chunks(
            request, prepared, recorder=recorder
        ):
            if chunk.content:
                yield chunk.content

    def generate_chunks(
        self,
        request: RagQuery,
        prepared: RagPrepared,
        recorder: TraceRecorder | None = None,
    ) -> Iterator[LlmStreamChunk]:
        """流式生成回答，产出完整分片（内容 + Token 用量 + 模型名）。"""
        with self._node(
            "LLM_GENERATE",
            {
                "model": prepared.model,
                "streaming": True,
            },
            recorder=recorder,
        ) as node:
            answer_parts: list[str] = []
            token_usage = TokenUsage()
            model_name = prepared.model
            for chunk in self._llm_client.stream_chat(
                question=prepared.standalone_query,
                model=prepared.model,
                history=prepared.history,
                summary=request.summary,
                context=prepared.context,
                rag_mode=prepared.need_rag,
                tool_result=prepared.tool_result,
            ):
                if chunk.content:
                    answer_parts.append(chunk.content)
                if chunk.token_usage.total_tokens > 0:
                    token_usage = chunk.token_usage
                if chunk.model:
                    model_name = chunk.model
                yield chunk
            if node is not None:
                node.set_output(
                    {
                        "modelName": model_name,
                        "answerChars": len("".join(answer_parts)),
                        "inputTokens": token_usage.input_tokens,
                        "outputTokens": token_usage.output_tokens,
                        "totalTokens": token_usage.total_tokens,
                    }
                )

    # ── 内部辅助 ────────────────────────────────
    def _resolve_route(
        self,
        request: RagQuery,
        resolved_query: ResolvedQuery,
    ) -> RouteDecision:
        """追问继承外部传入的上一轮路由；否则重新路由。"""
        last_route = request.last_route
        if (
            resolved_query.rewritten
            and last_route is not None
            and last_route.intent != L0Intent.CLARIFY
        ):
            return last_route.model_copy(
                update={
                    "inherit_context": True,
                    "router_path": "inherit",
                    "reason": "多轮追问，继承上一轮意图。",
                }
            )
        return self._query_router.route(
            query=resolved_query.standalone_query,
            history=request.history,
            preferred_knowledge_base_id=request.knowledge_base_id,
        )

    def postprocess_answer(
        self,
        raw_answer: str,
        prepared: RagPrepared,
        recorder: TraceRecorder | None = None,
    ) -> AnswerPostProcessResult:
        """回答后处理（引用校验）。业务层可直接复用。"""
        with self._node(
            "ANSWER_POST_PROCESS",
            recorder=recorder,
        ) as node:
            processed = self._answer_postprocessor.process(
                answer=raw_answer,
                documents=prepared.documents,
                rag_mode=prepared.need_rag,
                no_evidence=prepared.no_evidence,
            )
            if node is not None:
                node.set_output(
                    {
                        "answerStatus": (
                            processed.answer_status.value
                        ),
                        "usedCitationIndexes": (
                            processed.used_citation_indexes
                        ),
                        "invalidCitationIndexes": (
                            processed.invalid_citation_indexes
                        ),
                    }
                )
            return processed

    @contextmanager
    def _node(
        self,
        name: str,
        input_summary: dict | None = None,
        recorder: TraceRecorder | None = None,
    ):
        """Trace 节点上下文；没有 recorder 时为空操作。"""
        if recorder is None:
            yield None
            return
        with recorder.node(name, input_summary) as node:
            yield node

    @staticmethod
    def _skip_retrieval_stage(
        recorder: TraceRecorder | None,
        reason: str,
    ) -> None:
        """短路时不执行检索链路，按阶段记录 SKIPPED 节点。"""
        if recorder is None:
            return
        for name in (
            "RETRIEVAL_QUERY_REWRITE",
            "HYBRID_RETRIEVE",
            "RERANK",
            "CONTEXT_PACK",
        ):
            recorder.skip(name, reason=reason)

    @staticmethod
    def _merge_keywords(retrieval_query: RetrievalQuery) -> list[str]:
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
    def _build_clarification_answer(selection) -> str:
        """生成知识库选择提示。"""
        if not selection.candidates:
            return selection.reason

        candidates_text = "、".join(
            (
                f"{candidate.name}"
                f"（ID：{candidate.id}）"
            )
            for candidate in selection.candidates
        )
        return (
            f"{selection.reason}"
            f" 可选知识库：{candidates_text}。"
            "请选择一个知识库后重新提问。"
        )

    @staticmethod
    def _build_citations(
        documents: list[Document],
    ) -> list[dict[str, Any]]:
        """从最终上下文分片中构建引用信息。"""
        citations: list[dict[str, Any]] = []
        for document in documents:
            metadata = document.metadata
            citations.append(
                {
                    "chunkId": metadata.get("chunk_id"),
                    "documentId": metadata.get("document_id"),
                    "documentName": metadata.get("document_name"),
                    "chunkIndex": metadata.get("chunk_index"),
                    "citationIndex": metadata.get("citation_index"),
                    "contextTruncated": metadata.get(
                        "context_truncated", False
                    ),
                    "fusionScore": metadata.get("fusion_score"),
                    "vectorScore": metadata.get("vector_score"),
                    "keywordScore": metadata.get("keyword_score"),
                    "vectorRank": metadata.get("vector_rank"),
                    "keywordRank": metadata.get("keyword_rank"),
                    "retrievalSources": metadata.get(
                        "retrieval_sources", []
                    ),
                    "rerankScore": metadata.get("rerank_score"),
                    "rerankRank": metadata.get("rerank_rank"),
                    "content": document.page_content,
                }
            )
        return citations
