"""工作流节点共享的辅助函数。"""

from typing import Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig

from app.rag.schemas.query_schema import RagPrepared
from app.rag.settings import RagSettings
from app.rag.trace.trace_recorder import TraceRecorder
from app.rag.workflow.state import RagState


def get_recorder(config: RunnableConfig) -> TraceRecorder | None:
    """从运行配置中读取当前请求的 TraceRecorder。"""
    return config.get("configurable", {}).get("recorder")


def build_prepared(
    settings: RagSettings,
    state: RagState,
    *,
    intent: str | None = None,
    need_rag: bool = False,
    knowledge_base_id: int | None = None,
    context: str = "",
    documents: list[Document] | None = None,
    citations: list[dict[str, Any]] | None = None,
    candidate_count: int = 0,
    rerank_count: int = 0,
    context_document_count: int = 0,
    no_evidence: bool = False,
    clarification_answer: str | None = None,
    tool_result: str = "",
) -> RagPrepared:
    """组装各分支统一的 RagPrepared 返回对象。"""
    request = state["request"]
    resolved_query = state["resolved_query"]
    route_decision = state["route_decision"]

    return RagPrepared(
        question=request.question,
        standalone_query=resolved_query.standalone_query,
        model=request.model or settings.llm_model,
        history=request.history,
        intent=intent or route_decision.intent.value,
        need_rag=need_rag,
        knowledge_base_id=knowledge_base_id,
        route=route_decision,
        route_reason=route_decision.reason,
        context=context,
        documents=documents or [],
        citations=citations or [],
        candidate_count=candidate_count,
        rerank_count=rerank_count,
        context_document_count=context_document_count,
        no_evidence=no_evidence,
        clarification_answer=clarification_answer,
        tool_result=tool_result,
    )
