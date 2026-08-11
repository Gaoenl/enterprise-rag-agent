"""意图路由统一入口：规则 → 向量 → 默认兜底。

LLM 慢路径后续在规则与向量之间接入。
"""

from app.config import get_settings
from app.router.llm_intent_router import LlmIntentRouter
from app.router.query_router import QueryRouter
from app.router.vector_intent_router import VectorIntentRouter
from app.schemas.chat_schema import ChatHistoryMessage
from app.schemas.routing_schema import L0Intent, RouteDecision


class IntentRouter:
    """对外唯一路由入口，签名与 QueryRouter 保持一致。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._rules = QueryRouter()
        self._vector = VectorIntentRouter()
        self._llm = LlmIntentRouter()

    def route(
        self,
        query: str,
        history: list[ChatHistoryMessage],
        preferred_knowledge_base_id: int | None,
    ) -> RouteDecision:
        """规则快路径 → 向量快路径 → 默认兜底。"""
        rule_decision = self._rules.route(
            query=query,
            history=history,
            preferred_knowledge_base_id=preferred_knowledge_base_id,
        )

        # 规则确定命中（CLARIFY / CHAT / 显式选库 KNOWLEDGE）直接采用。
        if rule_decision.router_path != "fallback":
            return rule_decision

        # 规则未命中：走向量快路径。
        match = self._vector.match(query.strip())

        if match.score >= self._settings.intent_vector_threshold_high:
            return self._build_decision(
                match.intent,
                match.domain,
                match.score,
                router_path="vector",
                reason=f"向量命中代表句：{match.matched_example}",
            )
        # 向量低/中置信：交给 LLM 慢路径复核。
        if self._settings.intent_llm_enabled:
            llm_decision = self._llm.classify(query)
            if llm_decision is not None:
                # LLM 高置信直接采用。
                if llm_decision.confidence >= 0.85:
                    return llm_decision
                # LLM 中低置信：TOOL/CLARIFY 照常采用（语义明确），
                # 其余按 RAG 优先降级。
                if llm_decision.intent in (
                        L0Intent.TOOL,
                        L0Intent.CLARIFY,
                ):
                    return llm_decision
                return self._fallback(match.score, reason="LLM 置信度不足，按 RAG 优先降级。")
                # LLM 不可用/失败：按配置兜底。
        return self._fallback(match.score, reason="规则与向量未命中且 LLM 不可用，按 RAG 优先降级。")

    def _fallback(self, confidence: float, reason: str) -> RouteDecision:
        """低置信兜底：默认 RAG 优先，可按配置改为 chat / clarify。"""
        default = self._settings.intent_default_on_low_confidence
        if default == "chat":
            return RouteDecision(
                intent=L0Intent.CHAT,
                need_rag=False,
                confidence=confidence,
                router_path="fallback",
                reason=reason + "（配置降级普通对话）",
            )
        if default == "clarify":
            return RouteDecision(
                intent=L0Intent.CLARIFY,
                need_rag=False,
                confidence=confidence,
                router_path="fallback",
                reason=reason + "（配置降级引导澄清）",
            )
        return RouteDecision(
            intent=L0Intent.KNOWLEDGE,
            need_rag=True,
            confidence=confidence,
            router_path="fallback",
            reason=reason,
        )

    @staticmethod
    def _build_decision(
        intent: L0Intent,
        domain,
        confidence: float,
        router_path: str,
        reason: str,
    ) -> RouteDecision:
        """按意图构建 RouteDecision（need_rag 只在 KNOWLEDGE 时为真）。"""
        return RouteDecision(
            intent=intent,
            need_rag=intent == L0Intent.KNOWLEDGE,
            confidence=confidence,
            reason=reason,
            domain=domain,
            router_path=router_path,
        )