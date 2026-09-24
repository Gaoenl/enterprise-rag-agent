"""LangGraph 的条件路由函数。"""

from app.rag.schemas.routing_schema import L0Intent
from app.rag.workflow.state import RagState


def choose_route(state: RagState) -> str:
    """根据意图决定进入普通对话、澄清、工具或检索分支。"""
    route_decision = state["route_decision"]
    if route_decision.intent == L0Intent.CLARIFY:
        return "clarification"
    if route_decision.intent == L0Intent.TOOL:
        return "tool"
    if route_decision.need_rag:
        return "retrieval"
    return "chat"


def choose_knowledge_base(state: RagState) -> str:
    """知识库明确时进入检索，否则进入澄清。"""
    if state["knowledge_base_selection"].need_clarification:
        return "clarification"
    return "retrieval"


def choose_after_tool(state: RagState) -> str:
    """工具执行失败时进入澄清，成功时结束准备图。"""
    if state.get("clarification_answer"):
        return "clarification"
    return "end"
