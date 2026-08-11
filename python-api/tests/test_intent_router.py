"""意图路由单元测试（规则层 + 向量层 mock）。"""

from unittest.mock import MagicMock, patch

from app.router.intent_router import IntentRouter
from app.router.query_router import QueryRouter
from app.router.vector_intent_router import VectorMatch
from app.schemas.routing_schema import IntentDomain, L0Intent


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
            decision = router.route("出差路费怎么报销", [], None)
            assert decision.intent == L0Intent.KNOWLEDGE
            assert decision.domain == IntentDomain.EXPENSE
            assert decision.router_path == "vector"
