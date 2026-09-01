"""TraceRecorder unit tests."""

import pytest

from app.schemas.trace_schema import (
    TokenUsage,
    TraceNodeStatus,
    TraceStatus,
)
from app.rag.trace.trace_recorder import TraceRecorder


def create_recorder() -> TraceRecorder:
    """Create an isolated recorder for one request."""
    return TraceRecorder(
        trace_id=10001,
        request_id="request-10001",
        input_summary={
            "tenantId": 1,
            "question": "test question",
        },
    )


def test_node_records_success_and_output() -> None:
    recorder = create_recorder()

    with recorder.node(
        "QUERY_ROUTE",
        {"query": "test question"},
    ) as node:
        node.set_output(
            {
                "intent": "RAG_QA",
                "needRag": True,
            }
        )

    assert len(recorder.trace.nodes) == 1

    trace_node = recorder.trace.nodes[0]
    assert trace_node.name == "QUERY_ROUTE"
    assert trace_node.status == TraceNodeStatus.SUCCESS
    assert trace_node.finished_at is not None
    assert trace_node.latency_ms is not None
    assert trace_node.latency_ms >= 0
    assert trace_node.output_summary["needRag"] is True


def test_node_records_failure_without_swallowing_exception() -> None:
    recorder = create_recorder()

    with pytest.raises(RuntimeError, match="Rerank API timeout"):
        with recorder.node("RERANK"):
            raise RuntimeError("Rerank API timeout")

    trace_node = recorder.trace.nodes[0]
    assert trace_node.status == TraceNodeStatus.FAILED
    assert trace_node.finished_at is not None
    assert trace_node.error_message == "Rerank API timeout"


def test_finish_completes_successful_trace() -> None:
    recorder = create_recorder()

    with recorder.node("LLM_GENERATE"):
        pass

    trace = recorder.finish(
        output_summary={
            "answerStatus": "ANSWERED",
        },
        token_usage=TokenUsage(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
        ),
    )

    assert trace.status == TraceStatus.SUCCESS
    assert trace.finished_at is not None
    assert trace.latency_ms is not None
    assert trace.output["answerStatus"] == "ANSWERED"
    assert trace.token_usage.total_tokens == 120


def test_finish_preserves_degraded_status() -> None:
    recorder = create_recorder()

    recorder.mark_degraded(
        "Rerank failed, fallback to RRF"
    )

    trace = recorder.finish(
        output_summary={
            "answerStatus": "ANSWERED",
        }
    )

    assert trace.status == TraceStatus.DEGRADED
    assert trace.degraded_reasons == [
        "Rerank failed, fallback to RRF"
    ]


def test_mark_degraded_deduplicates_reason() -> None:
    recorder = create_recorder()

    recorder.mark_degraded("keyword retrieval failed")
    recorder.mark_degraded("keyword retrieval failed")

    assert recorder.trace.degraded_reasons == [
        "keyword retrieval failed"
    ]


def test_fail_completes_failed_trace() -> None:
    recorder = create_recorder()

    trace = recorder.fail(
        RuntimeError("PostgreSQL unavailable")
    )

    assert trace.status == TraceStatus.FAILED
    assert trace.finished_at is not None
    assert trace.latency_ms is not None
    assert trace.error_message == "PostgreSQL unavailable"

