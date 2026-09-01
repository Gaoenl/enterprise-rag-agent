"""聊天业务薄编排。

ChatService 只负责：请求校验、ChatRequest ↔ RagQuery 转换、
SSE 事件调度、ChatData 响应组装。RAG 编排全部委托 RagEngine。
"""

import logging
from collections.abc import Iterator

from fastapi import HTTPException

from app.config import get_settings
from app.rag.engine import (
    RagEngine,
    RagPrepared,
    RagQuery,
    RagResult,
)
from app.rag.trace.trace_recorder import TraceRecorder
from app.schemas.answer_schema import (
    AnswerPostProcessResult,
    AnswerStatus,
)
from app.schemas.chat_schema import ChatData, ChatRequest
from app.schemas.trace_schema import TokenUsage
from app.streaming.sse_encoder import SseEncoder

logger = logging.getLogger(__name__)


class ChatService:
    """聊天业务入口，内部复用 RagEngine。"""

    def __init__(
        self,
        engine: RagEngine | None = None,
    ) -> None:
        self._engine = engine or RagEngine()
        self._settings = get_settings()
        self._sse_encoder = SseEncoder()

    def answer(self, request: ChatRequest) -> ChatData:
        """执行同步聊天流程。"""
        self._validate_request(request)
        recorder = self._create_recorder(request)

        try:
            result = self._engine.query(
                self._to_rag_query(request),
                recorder=recorder,
            )
            trace = recorder.finish(
                output_summary=self._build_trace_output(
                    result=result,
                ),
                token_usage=result.token_usage,
            )
            return self._build_chat_data(
                request=request,
                result=result,
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
        rag_query = self._to_rag_query(request)

        try:
            yield self._sse_encoder.start(
                trace_id=request.trace_id,
                conversation_id=request.conversation_id,
            )

            prepared = self._engine.prepare(
                rag_query,
                recorder=recorder,
            )

            yield self._sse_encoder.route(
                intent=prepared.intent,
                need_rag=prepared.need_rag,
                knowledge_base_id=prepared.knowledge_base_id,
            )

            if prepared.need_rag:
                yield self._sse_encoder.retrieval(
                    candidate_count=prepared.candidate_count,
                    rerank_count=prepared.rerank_count,
                    context_document_count=(
                        prepared.context_document_count
                    ),
                )

            # 需要澄清时，不调用 LLM。
            if prepared.clarification_answer is not None:
                raw_answer = prepared.clarification_answer
                token_usage = TokenUsage()
                processed = AnswerPostProcessResult(
                    answer=raw_answer,
                    answer_status=(
                        AnswerStatus.CLARIFICATION_REQUIRED
                    ),
                )

            # 没有检索依据时，不调用 LLM。
            elif prepared.no_evidence:
                recorder.skip(
                    "LLM_GENERATE",
                    reason="检索无依据，未调用模型。",
                )
                raw_answer = (
                    self._settings.rag_empty_context_message
                )
                token_usage = TokenUsage()
                processed = self._engine.postprocess_answer(
                    raw_answer=raw_answer,
                    prepared=prepared,
                    recorder=recorder,
                )

            else:
                answer_parts: list[str] = []
                token_usage = TokenUsage()
                for chunk in self._engine.generate_chunks(
                    rag_query,
                    prepared,
                    recorder=recorder,
                ):
                    if chunk.content:
                        answer_parts.append(chunk.content)
                        yield self._sse_encoder.delta(
                            content=chunk.content
                        )
                    if chunk.token_usage.total_tokens > 0:
                        token_usage = chunk.token_usage

                raw_answer = "".join(answer_parts)
                processed = self._engine.postprocess_answer(
                    raw_answer=raw_answer,
                    prepared=prepared,
                    recorder=recorder,
                )

            trace = recorder.finish(
                output_summary=self._build_trace_output(
                    result=self._result_from_prepared(
                        prepared,
                        processed,
                        token_usage,
                    ),
                ),
                token_usage=token_usage,
            )

            chat_data = self._build_chat_data(
                request=request,
                prepared=prepared,
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
            yield self._sse_encoder.done(
                trace_id=request.trace_id
            )

        except GeneratorExit:
            recorder.fail(
                RuntimeError("SSE client disconnected")
            )
            logger.warning(
                "SSE client disconnected, trace_id=%s",
                request.trace_id,
            )
            raise

        except Exception as exception:
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

    # ── 转换与组装 ──────────────────────────────
    def _to_rag_query(self, request: ChatRequest) -> RagQuery:
        return RagQuery(
            question=request.question,
            history=request.history,
            summary=request.summary,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            knowledge_base_id=request.knowledge_base_id,
            model=request.model,
            last_route=request.last_route,
        )

    def _build_chat_data(
        self,
        request: ChatRequest,
        result=None,
        prepared: RagPrepared | None = None,
        processed: AnswerPostProcessResult | None = None,
        token_usage: TokenUsage | None = None,
        trace=None,
    ) -> ChatData:
        """构建统一聊天响应对象。"""
        if prepared is None:
            # 非流式：result 提供全部信息
            mode = (
                "clarify"
                if result.answer_status
                == AnswerStatus.CLARIFICATION_REQUIRED
                else "rag" if result.need_rag else "basic"
            )
            return ChatData(
                trace_id=request.trace_id,
                question=request.question,
                standalone_query=result.standalone_query,
                answer=result.answer,
                model=result.model,
                mode=mode,
                intent=result.intent,
                need_rag=result.need_rag,
                knowledge_base_id=result.knowledge_base_id,
                route_reason=result.route_reason,
                citations=result.citations,
                answer_status=result.answer_status,
                used_citation_indexes=[],
                invalid_citation_indexes=[],
                token_usage=result.token_usage,
                trace=trace,
            )

        # 流式：prepared + processed 组装
        if processed is None:
            raise ValueError("processed is required for stream")
        mode = (
            "clarify"
            if processed.answer_status
            == AnswerStatus.CLARIFICATION_REQUIRED
            else "rag" if prepared.need_rag else "basic"
        )
        return ChatData(
            trace_id=request.trace_id,
            question=request.question,
            standalone_query=prepared.standalone_query,
            answer=processed.answer,
            model=prepared.model,
            mode=mode,
            intent=prepared.intent,
            need_rag=prepared.need_rag,
            knowledge_base_id=prepared.knowledge_base_id,
            route_reason=prepared.route_reason,
            citations=prepared.citations,
            answer_status=processed.answer_status,
            used_citation_indexes=(
                processed.used_citation_indexes
            ),
            invalid_citation_indexes=(
                processed.invalid_citation_indexes
            ),
            token_usage=token_usage or TokenUsage(),
            trace=trace,
        )

    @staticmethod
    def _result_from_prepared(
        prepared: RagPrepared,
        processed: AnswerPostProcessResult,
        token_usage: TokenUsage,
    ) -> RagResult:
        return RagResult(
            answer=processed.answer,
            answer_status=processed.answer_status,
            intent=prepared.intent,
            need_rag=prepared.need_rag,
            standalone_query=prepared.standalone_query,
            model=prepared.model,
            knowledge_base_id=prepared.knowledge_base_id,
            citations=prepared.citations,
            token_usage=token_usage,
            route=prepared.route,
            route_reason=prepared.route_reason,
        )

    @staticmethod
    def _build_trace_output(result) -> dict:
        """构建 Trace 输出摘要。"""
        return {
            "answerStatus": result.answer_status.value,
            "intent": result.intent,
            "needRag": result.need_rag,
            "knowledgeBaseId": result.knowledge_base_id,
            "citationCount": len(result.citations),
        }

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
                "conversationId": request.conversation_id,
                "knowledgeBaseId": request.knowledge_base_id,
                "question": request.question[:1000],
            },
        )

    def _validate_request(self, request: ChatRequest) -> None:
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
