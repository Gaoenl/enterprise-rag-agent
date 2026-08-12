"""意图路由统一入口：规则短路 + 向量/LLM 并行 + 加权融合。"""
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.router.fusion import FusionConfig, fuse
from app.router.llm_intent_router import LlmIntentRouter
from app.router.query_router import QueryRouter
from app.router.vector_intent_router import VectorIntentRouter
from app.schemas.chat_schema import ChatHistoryMessage
from app.schemas.routing_schema import RouteDecision

# 向量匹配与 LLM 分类并行执行。
_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="rag-intent",
)
class IntentRouter:
    """对外唯一路由入口，签名与 QueryRouter 保持一致。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._rules = QueryRouter()
        self._vector = VectorIntentRouter()
        self._llm = LlmIntentRouter()
        self._fusion_config = FusionConfig(
            weight_llm=self._settings.intent_weight_llm,
            weight_vector=self._settings.intent_weight_vector,
            conf_high=self._settings.intent_conf_high,
            conf_low=self._settings.intent_conf_low,
            conf_gap=self._settings.intent_conf_gap,
            default_on_low_confidence=(
                self._settings.intent_default_on_low_confidence
            )
        )

    def route(
        self,
        query: str,
        history: list[ChatHistoryMessage],
        preferred_knowledge_base_id: int | None,
    ) -> RouteDecision:
        """规则短路 → 双路并行 → 加权融合 → 决策/降级。"""
        rule_decision = self._rules.route(
            query=query,
            history=history,
            preferred_knowledge_base_id=preferred_knowledge_base_id,
        )

        # 规则确定命中（CLARIFY / CHAT / 显式选库 KNOWLEDGE）直接采用。
        if rule_decision.router_path != "fallback":
            return rule_decision

        # 双路并行执行，互不阻塞。
        llm_future = _executor.submit(
            self._safe_llm,
            query,
        )
        vector_future = _executor.submit(
            self._safe_vector,
            query,
        )
        llm_decision = llm_future.result()
        vector_match = vector_future.result()
        # 加权融合（含单路失败降级）。
        return fuse(
            llm_decision=llm_decision,
            vector_match=vector_match,
            config=self._fusion_config,
        )

    def _safe_llm(self, query: str):
        """LLM 慢路径；失败或关闭返回 None 交给融合兜底。"""
        try:
            if self._settings.intent_llm_enabled:
                return self._llm.classify(query)
        except Exception:
            pass
        return None

    def _safe_vector(self, query: str):
        """向量快路径；失败返回 None 交给融合兜底。"""
        try:
            return self._vector.match(query.strip())
        except Exception:
            return None
