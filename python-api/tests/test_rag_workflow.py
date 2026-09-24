"""LangGraph 生成前工作流测试。"""

from contextlib import contextmanager
from types import SimpleNamespace

from langchain_core.documents import Document

from app.rag.schemas.context_schema import PackedContext
from app.rag.schemas.query_schema import RagQuery
from app.rag.schemas.routing_schema import (
    IntentDomain,
    KnowledgeBaseSelection,
    L0Intent,
    ResolvedQuery,
    RetrievalQuery,
    RouteDecision,
)
from app.rag.workflow.dependencies import (
    RagWorkflowDependencies,
    RetrievalDependencies,
    RoutingDependencies,
    ToolDependencies,
)
from app.rag.workflow.runner import RagWorkflow


@contextmanager
def fake_trace_node(*args, **kwargs):
    """测试中不记录真实 Trace。"""
    yield None


def make_dependencies(route, selection, documents=None):
    """构造穿过稳定依赖 seam 的内存实现。"""
    documents = documents or []
    settings = SimpleNamespace(
        llm_model="fake-model",
        retrieval_multi_query_enabled=False,
    )

    return RagWorkflowDependencies(
        routing=RoutingDependencies(
            settings=settings,
            trace_node=fake_trace_node,
            resolve_query=lambda request: ResolvedQuery(
                original_query=request.question,
                standalone_query=request.question,
                rewritten=False,
            ),
            route_intent=lambda request, resolved: route,
            skip_retrieval_stage=lambda recorder, reason: None,
        ),
        retrieval=RetrievalDependencies(
            settings=settings,
            trace_node=fake_trace_node,
            select_knowledge_base=lambda **kwargs: selection,
            rewrite_retrieval_query=lambda query: RetrievalQuery(
                semantic_query=query,
                keywords=["rag"],
            ),
            retrieve_documents=lambda **kwargs: (
                documents,
                SimpleNamespace(
                    vector_merged_count=len(documents),
                    keyword_count=0,
                    multi_query_count=0,
                    fused_count=len(documents),
                ),
            ),
            rerank_documents=lambda query, items: items,
            pack_documents=lambda items: PackedContext(
                text="packed context" if items else "",
                documents=items,
                total_chars=14 if items else 0,
            ),
            build_citations=lambda items: [],
            build_clarification_answer=lambda item: item.reason,
        ),
        tool=ToolDependencies(
            settings=settings,
            trace_node=fake_trace_node,
            is_tool_registered=lambda name: False,
            execute_tool=lambda name, tool_input: "",
        ),
    )


def test_graph_skips_retrieval_for_chat_route() -> None:
    route = RouteDecision(
        intent=L0Intent.CHAT,
        need_rag=False,
        confidence=0.9,
        reason="chat",
        domain=IntentDomain.GENERAL,
    )
    selection = KnowledgeBaseSelection(
        selection_type="none",
        reason="not needed",
    )
    workflow = RagWorkflow(make_dependencies(route, selection))

    prepared = workflow.prepare(RagQuery(question="hello"))

    assert prepared.intent == "CHAT"
    assert prepared.need_rag is False
    assert prepared.context == ""


def test_graph_runs_retrieval_for_knowledge_route() -> None:
    route = RouteDecision(
        intent=L0Intent.KNOWLEDGE,
        need_rag=True,
        confidence=0.9,
        reason="knowledge",
        domain=IntentDomain.GENERAL,
    )
    selection = KnowledgeBaseSelection(
        knowledge_base_id=7,
        selection_type="explicit",
        reason="selected",
    )
    documents = [
        Document(
            page_content="rag content",
            metadata={"chunk_id": 1},
        )
    ]
    workflow = RagWorkflow(
        make_dependencies(route, selection, documents)
    )

    prepared = workflow.prepare(RagQuery(question="what is rag"))

    assert prepared.need_rag is True
    assert prepared.knowledge_base_id == 7
    assert prepared.context == "packed context"
    assert prepared.candidate_count == 1
    assert prepared.rerank_count == 1


def test_graph_returns_clarification_when_kb_is_ambiguous() -> None:
    route = RouteDecision(
        intent=L0Intent.KNOWLEDGE,
        need_rag=True,
        confidence=0.9,
        reason="knowledge",
        domain=IntentDomain.GENERAL,
    )
    selection = KnowledgeBaseSelection(
        selection_type="ambiguous",
        need_clarification=True,
        reason="请选择知识库",
    )
    workflow = RagWorkflow(make_dependencies(route, selection))

    prepared = workflow.prepare(RagQuery(question="question"))

    assert prepared.intent == "CLARIFY"
    assert prepared.need_rag is False
    assert prepared.clarification_answer == "请选择知识库"
