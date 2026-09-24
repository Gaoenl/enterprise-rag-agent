"""查询解析、意图路由和非检索分支节点。"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.rag.workflow.dependencies import RoutingDependencies
from app.rag.workflow.nodes.common import build_prepared, get_recorder
from app.rag.workflow.state import RagState


def make_resolve_query_node(deps: RoutingDependencies):
    """创建多轮问题独立化节点。"""
    def resolve_query_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        request = state["request"]

        with deps.trace_node(
            "QUERY_RESOLVE",
            {"historyCount": len(request.history)},
            recorder=recorder,
        ) as node:
            resolved_query = deps.resolve_query(request)
            if node is not None:
                node.set_output({
                    "rewritten": resolved_query.rewritten,
                    "standaloneQuery": (
                        resolved_query.standalone_query[:1000]
                    ),
                })

        return {"resolved_query": resolved_query}

    return resolve_query_node


def make_route_intent_node(deps: RoutingDependencies):
    """创建意图路由节点，并处理追问路由继承。"""
    def route_intent_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        request = state["request"]
        resolved_query = state["resolved_query"]

        with deps.trace_node(
            "QUERY_ROUTE",
            recorder=recorder,
        ) as node:
            route_decision = deps.route_intent(
                request,
                resolved_query,
            )
            if node is not None:
                node.set_output({
                    "intent": route_decision.intent.value,
                    "domain": route_decision.domain.value,
                    "needRag": route_decision.need_rag,
                    "confidence": route_decision.confidence,
                    "reason": route_decision.reason,
                    "routerPath": route_decision.router_path,
                    "inheritContext": route_decision.inherit_context,
                })

        return {"route_decision": route_decision}

    return route_intent_node


def make_prepare_chat_node(deps: RoutingDependencies):
    """创建普通对话准备节点。"""
    def prepare_chat_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        deps.skip_retrieval_stage(
            get_recorder(config),
            "非 RAG 意图，跳过知识库检索。",
        )
        return {
            "prepared": build_prepared(
                deps.settings,
                state,
                intent=state["route_decision"].intent.value,
                need_rag=False,
            )
        }

    return prepare_chat_node


def make_prepare_clarification_node(deps: RoutingDependencies):
    """创建澄清准备节点，并记录被跳过的 RAG 阶段。"""
    def prepare_clarification_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        deps.skip_retrieval_stage(
            recorder,
            "需要澄清，跳过知识库检索链路。",
        )
        if recorder is not None:
            recorder.skip(
                "LLM_GENERATE",
                reason="需要澄清，未调用模型。",
            )

        return {
            "prepared": build_prepared(
                deps.settings,
                state,
                intent="CLARIFY",
                need_rag=False,
                clarification_answer=(
                    state.get("clarification_answer")
                    or state["route_decision"].reason
                ),
            )
        }

    return prepare_clarification_node
