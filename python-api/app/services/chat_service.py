"""聊天业务服务。

负责组织：
问题独立化 -> 意图路由 -> 知识库选择 -> 查询改写 ->
混合检索 -> 重排序 -> 上下文组装 -> LLM -> 回答后处理。
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from langchain_core.documents import Document

from app.clients.llm_client import LlmClient
from app.config import get_settings
from app.context.context_packer import ContextPacker
from app.factories.chat_model_factory import get_chat_model
from app.postprocessors.answer_postprocessor import AnswerPostProcessor
from app.resolver.conversation_query_resolver import (
    ConversationQueryResolver,
)
from app.retriever.hybrid_retriever import HybridRetriever
from app.retriever.keyword_extractor import KeywordExtractor
from app.rewriter.retrieval_query_rewriter import (
    RetrievalQueryRewriter,
)
from app.router.intent_router import IntentRouter
from app.router.knowledge_base_selector import (
    KnowledgeBaseSelector,
)
from app.router.query_router import QueryRouter
from app.schemas.answer_schema import (
    AnswerPostProcessResult,
    AnswerStatus,
)
from app.schemas.chat_schema import (
    ChatData,
    ChatHistoryMessage,
    ChatRequest,
)
from app.schemas.routing_schema import (
    L0Intent,
    ResolvedQuery,
    RetrievalQuery,
    RouteDecision,
)
from app.schemas.trace_schema import TokenUsage
from app.services.rerank_service import RerankService
from app.streaming.sse_encoder import SseEncoder
from app.tools.registry import is_registered, execute
from app.trace.trace_recorder import TraceRecorder

logger = logging.getLogger(__name__)


@dataclass
class ChatExecutionContext:
    """LLM 生成前准备完成后的内部数据。"""

    question: str
    standalone_query: str
    model: str
    history: list[ChatHistoryMessage]

    intent: str
    need_rag: bool
    route_reason: str | None = None
    knowledge_base_id: int | None = None

    context: str = ""
    documents: list[Document] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)

    candidate_count: int = 0
    rerank_count: int = 0
    context_document_count: int = 0

    no_evidence: bool = False
    clarification_answer: str | None = None
    tool_result: str = ""


class ChatService:
    """执行普通聊天和 RAG 问答流程。"""

    def __init__(self) -> None:
        """初始化聊天流程依赖。"""
        self._keyword_extractor = KeywordExtractor()
        self._settings = get_settings()

        # 复用同一个 LangChain 聊天模型。
        chat_model = get_chat_model()

        # 将多轮追问转换成独立问题。
        self._query_resolver = ConversationQueryResolver(
            chat_model
        )

        # 统一意图路由入口：规则 → 向量 → 兜底（后续接入 LLM）。
        self._query_router = IntentRouter()

        # 在当前租户范围内选择知识库。
        self._knowledge_base_selector = (
            KnowledgeBaseSelector()
        )

        # 将独立问题改写为检索查询。
        self._retrieval_query_rewriter = (
            RetrievalQueryRewriter(chat_model,self._keyword_extractor)
        )

        # 执行向量检索、关键词检索和 RRF 融合。
        self._retriever = HybridRetriever()

        # 对候选分片进行 Cross Encoder 重排序。
        self._rerank_service = RerankService()

        # 将重排序结果打包成模型上下文。
        self._context_packer = ContextPacker()

        # 调用大模型生成回答。
        self._llm_client = LlmClient()

        # 校验引用并清理最终回答。
        self._answer_postprocessor = AnswerPostProcessor()

        # 将流式事件编码为 SSE 文本。
        self._sse_encoder = SseEncoder()
        # 多轮追问时继承的上一轮路由决策（按会话维度，单实例共享可接受）。
        self._last_route: RouteDecision | None = None


    def answer(self, request: ChatRequest) -> ChatData:
        """执行同步聊天流程。"""
        self._validate_request(request)

        recorder = self._create_recorder(request)

        try:
            # 执行调用 LLM 前的公共流程。
            execution = self._prepare_execution(
                request=request,
                recorder=recorder,
            )

            # 需要用户选择知识库时直接返回澄清回答。
            if execution.clarification_answer is not None:
                raw_answer = execution.clarification_answer
                token_usage = TokenUsage()

                processed = AnswerPostProcessResult(
                    answer=raw_answer,
                    answer_status=(
                        AnswerStatus.CLARIFICATION_REQUIRED
                    ),
                )

            # RAG 未检索到有效依据时，不调用模型。
            elif execution.no_evidence:
                raw_answer = (
                    self._settings.rag_empty_context_message
                )
                token_usage = TokenUsage()

                processed = self._postprocess_answer(
                    raw_answer=raw_answer,
                    execution=execution,
                    recorder=recorder,
                )

            else:
                # 调用模型生成完整回答。
                with recorder.node(
                    "LLM_GENERATE",
                    {
                        "model": execution.model,
                        "streaming": False,
                    },
                ) as node:
                    llm_result = self._llm_client.chat(
                        question=execution.standalone_query,
                        model=execution.model,
                        history=execution.history,
                        summary=request.summary,
                        context=execution.context,
                        rag_mode=execution.need_rag,
                        tool_result=execution.tool_result,
                    )

                    raw_answer = llm_result.answer
                    token_usage = llm_result.token_usage

                    node.set_output(
                        {
                            "answerChars": len(raw_answer),
                            "inputTokens": (
                                token_usage.input_tokens
                            ),
                            "outputTokens": (
                                token_usage.output_tokens
                            ),
                            "totalTokens": (
                                token_usage.total_tokens
                            ),
                        }
                    )

                # 对完整模型回答进行引用检查。
                processed = self._postprocess_answer(
                    raw_answer=raw_answer,
                    execution=execution,
                    recorder=recorder,
                )

            # 完成整条 Trace。
            trace = recorder.finish(
                output_summary=self._build_trace_output(
                    execution=execution,
                    processed=processed,
                ),
                token_usage=token_usage,
            )

            # 组装同步接口响应。
            return self._build_chat_data(
                request=request,
                execution=execution,
                processed=processed,
                token_usage=token_usage,
                trace=trace,
            )

        except Exception as exception:
            recorder.fail(exception)

            logger.exception(
                "Chat failed, trace_id=%s",
                request.trace_id,
            )
            raise

    def stream_answer(
        self,
        request: ChatRequest,
    ) -> Iterator[str]:
        """执行聊天流程并返回 SSE 事件流。"""
        self._validate_request(request)

        recorder = self._create_recorder(request)

        try:
            # 通知 Java：Python 已开始处理请求。
            yield self._sse_encoder.start(
                trace_id=request.trace_id,
                conversation_id=request.conversation_id,
            )

            # 执行路由、检索、重排和上下文打包。
            execution = self._prepare_execution(
                request=request,
                recorder=recorder,
            )

            # 返回路由结果。
            yield self._sse_encoder.route(
                intent=execution.intent,
                need_rag=execution.need_rag,
                knowledge_base_id=(
                    execution.knowledge_base_id
                ),
            )

            # RAG 模式下返回检索阶段统计。
            if execution.need_rag:
                yield self._sse_encoder.retrieval(
                    candidate_count=(
                        execution.candidate_count
                    ),
                    rerank_count=execution.rerank_count,
                    context_document_count=(
                        execution.context_document_count
                    ),
                )

            # 需要用户选择知识库时，不调用 LLM。
            if execution.clarification_answer is not None:
                raw_answer = execution.clarification_answer
                token_usage = TokenUsage()

                processed = AnswerPostProcessResult(
                    answer=raw_answer,
                    answer_status=(
                        AnswerStatus.CLARIFICATION_REQUIRED
                    ),
                )

            # 没有检索依据时，不调用 LLM。
            elif execution.no_evidence:
                raw_answer = (
                    self._settings.rag_empty_context_message
                )
                token_usage = TokenUsage()

                processed = self._postprocess_answer(
                    raw_answer=raw_answer,
                    execution=execution,
                    recorder=recorder,
                )

            else:
                answer_parts: list[str] = []
                token_usage = TokenUsage()
                with recorder.node(
                    "LLM_GENERATE",
                    {
                        "streaming": True,
                    },
                ) as node:
                    # 持续读取 LangChain 模型分片。
                    for chunk in self._llm_client.stream_chat(
                        question=execution.standalone_query,
                        model=execution.model,
                        history=execution.history,
                        summary=request.summary,
                        context=execution.context,
                        rag_mode=execution.need_rag,
                        tool_result=execution.tool_result,
                    ):
                        # 文本分片立即发送给 Java。
                        if chunk.content:
                            answer_parts.append(chunk.content)

                            yield self._sse_encoder.delta(
                                content=chunk.content
                            )

                        # 最后一个分片可能包含 Token 用量。
                        if chunk.token_usage.total_tokens > 0:
                            token_usage = chunk.token_usage
                        if chunk.model:
                            model = chunk.model

                    # 拼接完整原始答案。
                    raw_answer = "".join(answer_parts)

                    node.set_output(
                        {
                            "modelName":model,
                            "answerChars": len(raw_answer),
                            "inputTokens": (
                                token_usage.input_tokens
                            ),
                            "outputTokens": (
                                token_usage.output_tokens
                            ),
                            "totalTokens": (
                                token_usage.total_tokens
                            ),
                        }
                    )

                # 流结束后统一校验引用。
                processed = self._postprocess_answer(
                    raw_answer=raw_answer,
                    execution=execution,
                    recorder=recorder,
                )

            # 正常完成 Trace。
            trace = recorder.finish(
                output_summary=self._build_trace_output(
                    execution=execution,
                    processed=processed,
                ),
                token_usage=token_usage,
            )

            # final 是 Java 应持久化的最终权威结果。
            chat_data = self._build_chat_data(
                request=request,
                execution=execution,
                processed=processed,
                token_usage=token_usage,
                trace=trace,
            )

            yield self._sse_encoder.final(
                data=chat_data.model_dump(
                    by_alias=True,
                    mode="json",
                )
            )

            # 通知 Java 流正常结束。
            yield self._sse_encoder.done(
                trace_id=request.trace_id
            )

        except GeneratorExit:
            # Java 或前端断开连接。
            recorder.fail(
                RuntimeError("SSE client disconnected")
            )

            logger.warning(
                "SSE client disconnected, trace_id=%s",
                request.trace_id,
            )
            raise

        except Exception as exception:
            # SSE 建立后不能再修改 HTTP 状态码。
            recorder.fail(exception)

            logger.exception(
                "Streaming chat failed, trace_id=%s",
                request.trace_id,
            )

            yield self._sse_encoder.error(
                code="CHAT_STREAM_FAILED",
                message=str(exception),
                trace_id=request.trace_id,
            )

            yield self._sse_encoder.done(
                trace_id=request.trace_id
            )

    def _prepare_execution(
        self,
        request: ChatRequest,
        recorder: TraceRecorder,
    ) -> ChatExecutionContext:
        """执行 LLM 生成前的公共流程。"""
        model = request.model or self._settings.llm_model

        # 将依赖历史的问题转换成独立问题。
        with recorder.node(
            "QUERY_RESOLVE",
            {
                "historyCount": len(request.history)
            },
        ) as node:
            resolved_query = self._query_resolver.resolve(
                question=request.question,
                history=request.history,
            )

            node.set_output(
                {
                    "rewritten": resolved_query.rewritten,
                    "standaloneQuery": (
                        resolved_query.standalone_query[:1000]
                    ),
                }
            )

        # 判断当前问题是否需要使用 RAG。
        with recorder.node("QUERY_ROUTE") as node:
            if resolved_query.rewritten and self._last_route is not None:
                route=self._last_route.model_copy(
                    update={
                        "inherit_context": True,
                        "router_path": "inherit",
                        "reason": "多轮追问，继承上一轮意图。",
                    }

                )
            else:
                route = self._query_router.route(
                    query=resolved_query.standalone_query,
                    history=request.history,
                    preferred_knowledge_base_id=(
                        request.knowledge_base_id
                    ),
                )
                self._last_route = route

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

        # TOOL 意图：执行工具，结果作为上下文喂给 LLM，不检索知识库。
        if route.intent == L0Intent.TOOL:
            # 工具缺失或未注册时引导澄清，不让请求失败。
            if route.tool is None or not is_registered(route.tool.tool):
                return ChatExecutionContext(
                    question=request.question,
                    standalone_query=(
                        resolved_query.standalone_query
                    ),
                    model=model,
                    history=request.history,
                    intent="CLARIFY",
                    need_rag=False,
                    route_reason=route.reason,
                    clarification_answer=(
                        "当前请求需要调用工具，但该工具尚未开通，"
                        "请稍后再试或换一种问法。"
                    ),
                )
                # 记录工具执行过程。
                # 记录工具执行过程。
            with recorder.node(
                    "TOOL_EXECUTE",
                    {
                        "tool": route.tool.tool,
                        "input": str(route.tool.tool_input)[:500],
                    },
            ) as node:
                try:
                    tool_result = execute(
                        route.tool.tool,
                        route.tool.tool_input,
                    )
                except Exception as exception:
                    node.set_output(
                        {"error": str(exception)[:500]}
                    )
                    logger.exception(
                        "工具执行失败, tool=%s",
                        route.tool.tool,
                    )
                    return ChatExecutionContext(
                        question=request.question,
                        standalone_query=(
                            resolved_query.standalone_query
                        ),
                        model=model,
                        history=request.history,
                        intent="CLARIFY",
                        need_rag=False,
                        route_reason=route.reason,
                        clarification_answer=(
                            f"工具执行失败：{exception}，"
                            "请稍后再试或换一种问法。"
                        ),
                    )
                node.set_output(
                    {"resultChars": len(tool_result)}
                )
        # 普通对话直接进入 LLM。
        if not route.need_rag:
            return ChatExecutionContext(
                question=request.question,
                standalone_query=(
                    resolved_query.standalone_query
                ),
                model=model,
                history=request.history,
                intent=route.intent.value,
                need_rag=False,
                route_reason=route.reason,
            )

        # 在当前租户允许访问的范围内选择知识库。
        with recorder.node(
            "KNOWLEDGE_BASE_SELECT"
        ) as node:
            selection = (
                self._knowledge_base_selector.select(
                    tenant_id=request.tenant_id,
                    user_id=request.user_id,
                    preferred_knowledge_base_id=(
                        request.knowledge_base_id
                    ),
                    query=resolved_query.standalone_query,
                    domain=route.domain.value,
                )
            )

            node.set_output(
                {
                    "knowledgeBaseId": (
                        selection.knowledge_base_id
                    ),
                    "selectionType": (
                        selection.selection_type
                    ),
                    "needClarification": (
                        selection.need_clarification
                    ),
                }
            )

        # 无法确定知识库时返回澄清响应。
        if selection.need_clarification:
            return ChatExecutionContext(
                question=request.question,
                standalone_query=(
                    resolved_query.standalone_query
                ),
                model=model,
                history=request.history,
                intent="CLARIFY",
                need_rag=False,
                route_reason=selection.reason,
                clarification_answer=(
                    self._build_clarification_answer(
                        selection
                    )
                ),
            )

        selected_knowledge_base_id = (
            selection.knowledge_base_id
        )

        # 生成语义查询和关键词。
        with recorder.node(
            "RETRIEVAL_QUERY_REWRITE"
        ) as node:
            retrieval_query = (
                self._retrieval_query_rewriter.rewrite(
                    resolved_query.standalone_query
                )
            )

            node.set_output(
                {
                    "semanticQuery": (
                        retrieval_query.semantic_query[:1000]
                    ),
                    "keywords": retrieval_query.keywords,
                }
            )

        # 执行混合检索和 RRF 融合。
        with recorder.node(
            "HYBRID_RETRIEVE"
        ) as node:
            # 合并模型生成的关键词同义变体（去重后用于关键词检索）。
            keywords = self._merge_retrieval_keywords(
                retrieval_query
            )
            retrieved_documents = self._retriever.retrieve(
                semantic_query=(
                    retrieval_query.semantic_query
                ),
                keywords=keywords,
                tenant_id=request.tenant_id,
                knowledge_base_id=(
                    selected_knowledge_base_id
                ),
                alternative_queries=(
                    retrieval_query.alternative_queries
                    if self._settings.retrieval_multi_query_enabled
                    else []
                ),
            )

            candidate_count = len(retrieved_documents)

            node.set_output(
                {
                    "candidateCount": candidate_count,
                }
            )

        # 对候选分片进行重排序。
        with recorder.node("RERANK") as node:
            reranked_documents = (
                self._rerank_service.rerank(
                    query=resolved_query.standalone_query,
                    documents=retrieved_documents,
                )
            )

            rerank_count = len(reranked_documents)

            node.set_output(
                {
                    "inputCount": candidate_count,
                    "resultCount": rerank_count,
                }
            )

        # 将重排序结果装入上下文预算。
        with recorder.node("CONTEXT_PACK") as node:
            packed_context = self._context_packer.pack(
                reranked_documents
            )

            documents = packed_context.documents
            context = packed_context.text
            citations = self._build_citations(
                documents
            )

            context_document_count = len(documents)

            node.set_output(
                {
                    "documentCount": (
                        context_document_count
                    ),
                    "totalChars": (
                        packed_context.total_chars
                    ),
                    "truncated": (
                        packed_context.truncated
                    ),
                }
            )

        return ChatExecutionContext(
            question=request.question,
            standalone_query=(
                resolved_query.standalone_query
            ),
            model=model,
            history=request.history,
            intent=route.intent.value,
            need_rag=True,
            route_reason=route.reason,
            knowledge_base_id=(
                selected_knowledge_base_id
            ),
            context=context,
            documents=documents,
            citations=citations,
            candidate_count=candidate_count,
            rerank_count=rerank_count,
            context_document_count=(
                context_document_count
            ),
            no_evidence=not context.strip(),
        )

    def _postprocess_answer(
        self,
        raw_answer: str,
        execution: ChatExecutionContext,
        recorder: TraceRecorder,
    ) -> AnswerPostProcessResult:
        """清理回答并校验引用编号。"""
        with recorder.node(
            "ANSWER_POST_PROCESS"
        ) as node:
            processed = (
                self._answer_postprocessor.process(
                    answer=raw_answer,
                    documents=execution.documents,
                    rag_mode=execution.need_rag,
                    no_evidence=execution.no_evidence,
                )
            )

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

    @staticmethod
    def _build_trace_output(
        execution: ChatExecutionContext,
        processed: AnswerPostProcessResult,
    ) -> dict[str, Any]:
        """构建 Trace 输出摘要。"""
        return {
            "answerStatus": (
                processed.answer_status.value
            ),
            "intent": execution.intent,
            "needRag": execution.need_rag,
            "knowledgeBaseId": (
                execution.knowledge_base_id
            ),
            "citationCount": len(
                execution.citations
            ),
        }

    @staticmethod
    def _build_chat_data(
        request: ChatRequest,
        execution: ChatExecutionContext,
        processed: AnswerPostProcessResult,
        token_usage: TokenUsage,
        trace,
    ) -> ChatData:
        """构建统一聊天响应对象。"""
        if execution.clarification_answer is not None:
            mode = "clarify"
        elif execution.need_rag:
            mode = "rag"
        else:
            mode = "basic"

        return ChatData(
            trace_id=request.trace_id,
            question=request.question,
            standalone_query=(
                execution.standalone_query
            ),
            answer=processed.answer,
            model=execution.model,
            mode=mode,
            intent=execution.intent,
            need_rag=execution.need_rag,
            knowledge_base_id=(
                execution.knowledge_base_id
            ),
            route_reason=execution.route_reason,
            citations=execution.citations,
            answer_status=(
                processed.answer_status
            ),
            used_citation_indexes=(
                processed.used_citation_indexes
            ),
            invalid_citation_indexes=(
                processed.invalid_citation_indexes
            ),
            token_usage=token_usage,
            trace=trace,
        )

    @staticmethod
    def _create_recorder(
        request: ChatRequest,
    ) -> TraceRecorder:
        """创建当前请求的 TraceRecorder。"""
        return TraceRecorder(
            trace_id=request.trace_id,
            request_id=request.request_id,
            input_summary={
                "tenantId": request.tenant_id,
                "userId": request.user_id,
                "conversationId": (
                    request.conversation_id
                ),
                "knowledgeBaseId": (
                    request.knowledge_base_id
                ),
                "question": request.question[:1000],
            },
        )

    @staticmethod
    def _merge_retrieval_keywords(
        retrieval_query: RetrievalQuery,
    ) -> list[str]:
        """合并关键词与模型生成的同义词变体，去重后返回。"""
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
    def _build_clarification_answer(
        selection,
    ) -> str:
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
                    "documentId": metadata.get(
                        "document_id"
                    ),
                    "documentName": metadata.get(
                        "document_name"
                    ),
                    "chunkIndex": metadata.get(
                        "chunk_index"
                    ),
                    "citationIndex": metadata.get(
                        "citation_index"
                    ),
                    "contextTruncated": metadata.get(
                        "context_truncated",
                        False,
                    ),
                    "fusionScore": metadata.get(
                        "fusion_score"
                    ),
                    "vectorScore": metadata.get(
                        "vector_score"
                    ),
                    "keywordScore": metadata.get(
                        "keyword_score"
                    ),
                    "vectorRank": metadata.get(
                        "vector_rank"
                    ),
                    "keywordRank": metadata.get(
                        "keyword_rank"
                    ),
                    "retrievalSources": metadata.get(
                        "retrieval_sources",
                        [],
                    ),
                    "rerankScore": metadata.get(
                        "rerank_score"
                    ),
                    "rerankRank": metadata.get(
                        "rerank_rank"
                    ),
                    "content": document.page_content,
                }
            )

        return citations

    def _validate_request(
        self,
        request: ChatRequest,
    ) -> None:
        """校验聊天请求。"""
        if not request.question.strip():
            raise HTTPException(
                status_code=400,
                detail="question must not be blank",
            )

        if len(request.question) > 10000:
            raise HTTPException(
                status_code=400,
                detail="question length must be <= 10000",
            )

        if len(request.history) > 100:
            raise HTTPException(
                status_code=400,
                detail="history size must be <= 100",
            )

        if request.model and (
            request.model != self._settings.llm_model
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Chat model mismatch: "
                    f"request={request.model}, "
                    f"configured={self._settings.llm_model}"
                ),
            )
