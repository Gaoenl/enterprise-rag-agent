"""组装并编译生成前的 LangGraph 工作流。"""

from langgraph.graph import END, START, StateGraph

from app.rag.workflow.dependencies import RagWorkflowDependencies
from app.rag.workflow.nodes.retrieval import (
    make_pack_context_node,
    make_rerank_documents_node,
    make_retrieve_hybrid_node,
    make_rewrite_retrieval_query_node,
    make_select_knowledge_base_node,
)
from app.rag.workflow.nodes.query import (
    make_prepare_chat_node,
    make_prepare_clarification_node,
    make_resolve_query_node,
    make_route_intent_node,
)
from app.rag.workflow.nodes.tool import make_prepare_tool_node
from app.rag.workflow.routing import (
    choose_after_tool,
    choose_knowledge_base,
    choose_route,
)
from app.rag.workflow.state import RagState


def build_prepare_graph(deps: RagWorkflowDependencies):
    """创建生成前工作流，并在构造节点时注入稳定依赖。"""
    builder = StateGraph(RagState)

    # 查询解析、路由和短路径准备节点。
    builder.add_node(
        "resolve_query",
        make_resolve_query_node(deps.routing),
    )
    builder.add_node(
        "route_intent",
        make_route_intent_node(deps.routing),
    )
    builder.add_node(
        "prepare_chat",
        make_prepare_chat_node(deps.routing),
    )
    builder.add_node(
        "prepare_clarification",
        make_prepare_clarification_node(deps.routing),
    )
    builder.add_node(
        "prepare_tool",
        make_prepare_tool_node(deps.tool),
    )
    builder.add_node(
        "select_knowledge_base",
        make_select_knowledge_base_node(deps.retrieval),
    )
    builder.add_node(
        "rewrite_retrieval_query",
        make_rewrite_retrieval_query_node(deps.retrieval),
    )
    builder.add_node(
        "retrieve_hybrid",
        make_retrieve_hybrid_node(deps.retrieval),
    )
    builder.add_node(
        "rerank_documents",
        make_rerank_documents_node(deps.retrieval),
    )
    builder.add_node(
        "pack_context",
        make_pack_context_node(deps.retrieval),
    )

    # 先完成查询独立化，再根据意图选择后续路径。
    builder.add_edge(START, "resolve_query")
    builder.add_edge("resolve_query", "route_intent")
    builder.add_conditional_edges(
        "route_intent",
        choose_route,
        {
            "chat": "prepare_chat",
            "clarification": "prepare_clarification",
            "tool": "prepare_tool",
            "retrieval": "select_knowledge_base",
        },
    )
    builder.add_conditional_edges(
        "select_knowledge_base",
        choose_knowledge_base,
        {
            "clarification": "prepare_clarification",
            "retrieval": "rewrite_retrieval_query",
        },
    )
    builder.add_conditional_edges(
        "prepare_tool",
        choose_after_tool,
        {
            "clarification": "prepare_clarification",
            "end": END,
        },
    )

    # 知识库明确后，依次执行检索、重排和上下文打包。
    builder.add_edge(
        "rewrite_retrieval_query",
        "retrieve_hybrid",
    )
    builder.add_edge("retrieve_hybrid", "rerank_documents")
    builder.add_edge("rerank_documents", "pack_context")
    # 所有分支最终都返回 RagPrepared，LLM 生成在图外执行。
    builder.add_edge("prepare_chat", END)
    builder.add_edge("prepare_clarification", END)
    builder.add_edge("pack_context", END)

    return builder.compile()
