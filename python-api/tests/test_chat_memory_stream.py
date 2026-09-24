"""Regression tests for chat memory integration in the streaming path."""

from types import SimpleNamespace

from app.apps.chat.chat_service import ChatService
from app.rag.trace.trace_recorder import TraceRecorder
from app.schemas.answer_schema import (
    AnswerPostProcessResult,
    AnswerStatus,
)
from app.schemas.chat_schema import ChatRequest
from app.schemas.trace_schema import TokenUsage


class FakeMemory:
    def __init__(self) -> None:
        self.completed = False
        self.summarized = False
        self.failed = False

    def begin(self, request: ChatRequest):
        recorder = TraceRecorder(
            trace_id=request.trace_id,
            request_id=request.request_id,
            input_summary={"question": request.question},
        )
        return SimpleNamespace(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            user_message_id=101,
            trace_id=request.trace_id,
            history=[],
            summary="",
            last_route=None,
            trace=recorder.trace,
        )

    def complete(self, context, data) -> None:
        self.completed = True

    def fail(self, context, trace) -> None:
        self.failed = True

    def summarize_if_needed(self, context, summary_service) -> None:
        self.summarized = True

    def close(self) -> None:
        pass


class FakeEngine:
    def prepare(self, request, recorder=None):
        return SimpleNamespace(
            question=request.question,
            standalone_query=request.question,
            model="fake-model",
            history=request.history,
            intent="CHAT",
            need_rag=False,
            knowledge_base_id=None,
            route=None,
            route_reason=None,
            context="",
            documents=[],
            citations=[],
            candidate_count=0,
            rerank_count=0,
            context_document_count=0,
            no_evidence=False,
            clarification_answer=None,
            tool_result="",
        )

    def generate_chunks(self, request, prepared, recorder=None):
        yield SimpleNamespace(
            content="你好",
            token_usage=TokenUsage(
                outputTokens=2,
                totalTokens=2,
            ),
        )

    def postprocess_answer(self, raw_answer, prepared, recorder=None):
        return AnswerPostProcessResult(
            answer=raw_answer,
            answer_status=AnswerStatus.GENERAL,
        )


def test_stream_answer_commits_and_summarizes() -> None:
    memory = FakeMemory()
    service = ChatService(
        memory=memory,
        summary_service=object(),
        engine=FakeEngine(),
    )
    request = ChatRequest(
        question="你好",
        tenantId=1,
        userId=2,
        traceId=1001,
        requestId="stream-memory-001",
        conversationId=2001,
    )

    events = list(service.stream_answer(request))

    assert any("event: final" in event for event in events)
    assert any("event: done" in event for event in events)
    assert memory.completed is True
    assert memory.summarized is True
    assert memory.failed is False
