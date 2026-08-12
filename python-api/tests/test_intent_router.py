"""意图路由单元测试：规则层 + 融合层 + 集成（向量/LLM mock）。"""

from unittest.mock import MagicMock, patch

from app.router.fusion import FusionConfig, fuse
from app.router.intent_router import IntentRouter
from app.router.query_router import QueryRouter
from app.router.vector_intent_router import VectorMatch
from app.schemas.routing_schema import (
    IntentDomain,
    L0Intent,
    RouteDecision,
    ToolRequest,
)


class TestQueryRouter:
    def setup_method(self):
        self.router = QueryRouter()

    def test_empty_query_clarify(self):
        decision = self.router.route("", [], None)
        assert decision.intent == L0Intent.CLARIFY
        assert decision.need_rag is False

    def test_greeting_chat(self):
        decision = self.router.route("你好", [], None)
        assert decision.intent == L0Intent.CHAT
        assert decision.need_rag is False

    def test_explicit_kb_knowledge(self):
        decision = self.router.route("报销标准", [], 1)
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.need_rag is True

    def test_default_fallback_knowledge(self):
        decision = self.router.route("差旅费能报多少", [], None)
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.need_rag is True
        assert decision.router_path == "fallback"


FUSION_CONFIG = FusionConfig()


class TestFusion:
    def test_both_agree_knowledge(self):
        llm = RouteDecision(
            intent=L0Intent.KNOWLEDGE,
            need_rag=True,
            confidence=0.9,
            reason="",
            domain=IntentDomain.EXPENSE,
            router_path="llm",
        )
        vec = VectorMatch(
            intent=L0Intent.KNOWLEDGE,
            domain=IntentDomain.EXPENSE,
            score=0.82,
            matched_example="报销标准",
        )
        decision = fuse(llm, vec, FUSION_CONFIG)
        # 归一化：(0.7*0.9 + 0.3*0.82) / 1.0 = 0.876 >= 0.85
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.domain == IntentDomain.EXPENSE
        assert decision.router_path == "fusion:both"

    def test_vector_only_high_confidence(self):
        vec = VectorMatch(
            intent=L0Intent.KNOWLEDGE,
            domain=IntentDomain.EXPENSE,
            score=0.9,
            matched_example="差旅费能报多少",
        )
        decision = fuse(None, vec, FUSION_CONFIG)
        # 归一化：0.3*0.9 / 0.3 = 0.9 >= 0.85，不会被权重压低。
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.domain == IntentDomain.EXPENSE
        assert decision.router_path == "fusion:vector"

    def test_disagreement_falls_back_to_knowledge(self):
        llm = RouteDecision(
            intent=L0Intent.CHAT,
            need_rag=False,
            confidence=0.55,
            reason="",
            router_path="llm",
        )
        vec = VectorMatch(
            intent=L0Intent.KNOWLEDGE,
            domain=IntentDomain.GENERAL,
            score=0.5,
            matched_example="默认",
        )
        decision = fuse(llm, vec, FUSION_CONFIG)
        # 归一化后 CHAT=0.55、KNOWLEDGE=0.5，分差 0.05 < gap 0.15 → 分歧降级。
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.router_path == "fusion:fallback"

    def test_chat_medium_confidence_falls_back(self):
        llm = RouteDecision(
            intent=L0Intent.CHAT,
            need_rag=False,
            confidence=0.7,
            reason="",
            router_path="llm",
        )
        decision = fuse(llm, None, FUSION_CONFIG)
        # 归一化 0.7：conf_low <= 0.7 < conf_high，CHAT 降级防漏检。
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.router_path == "fusion:fallback"

    def test_tool_direct(self):
        llm = RouteDecision(
            intent=L0Intent.TOOL,
            need_rag=False,
            confidence=0.9,
            reason="",
            router_path="llm",
            tool=ToolRequest(
                tool="calculator",
                tool_input={"expression": "2**10"},
            ),
        )
        decision = fuse(llm, None, FUSION_CONFIG)
        assert decision.intent == L0Intent.TOOL
        assert decision.tool is not None
        assert decision.tool.tool == "calculator"
        assert decision.router_path == "fusion:llm"

    def test_both_failed_fallback(self):
        decision = fuse(None, None, FUSION_CONFIG)
        assert decision.intent == L0Intent.KNOWLEDGE
        assert decision.router_path == "fusion:fallback"


class TestIntentRouter:
    def test_vector_high_confidence(self):
        fake_match = VectorMatch(
            intent=L0Intent.KNOWLEDGE,
            domain=IntentDomain.EXPENSE,
            score=0.9,
            matched_example="差旅费能报多少",
        )
        with (
            patch(
                "app.router.vector_intent_router.VectorIntentRouter.__init__",
                return_value=None,
            ),
            patch(
                "app.router.llm_intent_router.LlmIntentRouter.__init__",
                return_value=None,
            ),
        ):
            router = IntentRouter()
            router._vector.match = MagicMock(return_value=fake_match)
            # 模拟 LLM 路失败/无结果，验证单路向量融合。
            router._llm.classify = MagicMock(return_value=None)
            decision = router.route("出差路费怎么报销", [], None)
            assert decision.intent == L0Intent.KNOWLEDGE
            assert decision.domain == IntentDomain.EXPENSE
            assert decision.router_path == "fusion:vector"
