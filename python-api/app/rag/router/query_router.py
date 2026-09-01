"""根据独立问题判断是否需要进入 RAG 检索流程。"""
import re

from app.schemas.chat_schema import ChatHistoryMessage
from app.rag.schemas.routing_schema import RouteDecision, L0Intent


class QueryRouter:
    """第一版规则路由器，后续可增加 LLM 结构化分类。"""

    _GREETING_PATTERN = re.compile(
        r"^(你好|您好|嗨|hello|hi|早上好|下午好|晚上好)[！!。. ]*$",
        re.IGNORECASE,
    )

    def route(
            self,
            query: str,
            history: list[ChatHistoryMessage],
            preferred_knowledge_base_id: int | None,
    ) -> RouteDecision:
        """返回本次请求的意图和 RAG 决策。"""
        normalized_query = query.strip()

        # 空问题无法进入问答流程，需要用户补充问题。
        if not normalized_query:
            return RouteDecision(
                intent=L0Intent.CLARIFY,
                need_rag=False,
                confidence=1.0,
                reason="当前问题为空。",
            )

        # 用户明确选择知识库时，优先进入 RAG。
        if preferred_knowledge_base_id is not None:
            return RouteDecision(
                intent=L0Intent.KNOWLEDGE,
                need_rag=True,
                confidence=1.0,
                reason="用户已明确选择知识库。",
            )

        # 纯问候不需要检索企业知识库。
        if self._GREETING_PATTERN.fullmatch(normalized_query):
            return RouteDecision(
                intent=L0Intent.CHAT,
                need_rag=False,
                confidence=0.98,
                reason="当前问题属于普通问候。",
            )

        # 未命中确定性规则：按「宁可检索、不要漏检」默认进入知识检索，
        # 检索无结果时由下游降级为普通回答。
        return RouteDecision(
            intent=L0Intent.KNOWLEDGE,
            need_rag=True,
            router_path="fallback",
            confidence=0.6,
            reason="未命中确定性规则，按 RAG 优先策略默认进入知识检索。",
        )