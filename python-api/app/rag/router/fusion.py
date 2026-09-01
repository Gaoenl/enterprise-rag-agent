"""三路意图融合：规则短路由 IntentRouter 处理，这里只做 向量/LLM 加权投票。

决策规则：
1. 双路均无结果 → 默认 KNOWLEDGE（RAG 优先）；
2. TOOL / CLARIFY：语义明确，即使单路命中或分差不明显也直接采用；
3. 双路分歧（最高分与次高分差距 < conf_gap）→ 默认降级（默认 KNOWLEDGE）；
4. 置信度分级：≥ conf_high 直接采用；conf_low ~ conf_high 时
   CHAT 降级为默认检索（防漏检），KNOWLEDGE/TOOL/CLARIFY 照常采用；
5. < conf_low → 按 default_on_low_confidence 降级。
"""
from dataclasses import dataclass

from app.rag.router.vector_intent_router import VectorMatch
from app.rag.schemas.routing_schema import RouteDecision, L0Intent, IntentDomain


@dataclass
class FusionConfig:
    """融合参数（与 config.py 的 intent_* 对齐）。"""

    weight_llm: float = 0.7
    weight_vector: float = 0.3
    conf_high: float = 0.85
    conf_low: float = 0.6
    conf_gap: float = 0.15
    default_on_low_confidence: str = "knowledge"

def fuse(
    llm_decision: RouteDecision | None,
    vector_match: VectorMatch | None,
    config: FusionConfig,
) -> RouteDecision:
    """合并向量与 LLM 结果，输出最终 RouteDecision。"""
    scores: dict[L0Intent, float] = {}
    domain_by_intent: dict[L0Intent, IntentDomain] = {}
    source_by_intent: dict[L0Intent, str] = {}
    llm_tool: dict[L0Intent, object] = {}
    llm_reason: str = ""
    if llm_decision is not None:
        intent = llm_decision.intent
        scores[intent] = config.weight_llm * llm_decision.confidence
        domain_by_intent[intent] = llm_decision.domain
        source_by_intent[intent] = "llm"
        llm_tool[intent] = llm_decision.tool
        llm_reason = llm_decision.reason
    if vector_match is not None:
        intent = vector_match.intent
        add = config.weight_vector * vector_match.score
        scores[intent] = scores.get(intent, 0.0) + add
        domain_by_intent.setdefault(intent, vector_match.domain)
        # 双路都命中同一意图时标记 both；否则标记 vector。
        if intent in source_by_intent:
            source_by_intent[intent] = "both"
        else:
            source_by_intent[intent] = "vector"
    source_scores = {
        "llm": (
            llm_decision.confidence
            if llm_decision is not None
            else 0.0
        ),
        "vector": (
            vector_match.score
            if vector_match is not None
            else 0.0
        ),
    }
    # 双路均失败 → RAG 优先兜底。
    if not scores:
        return _build(
            intent=L0Intent.KNOWLEDGE,
            domain=IntentDomain.GENERAL,
            confidence=0.5,
            router_path="fusion:fallback",
            reason="意图识别两路均失败，按 RAG 优先降级。",
            source_scores=source_scores,
        )

    # 归一化：加权得分除以该意图被投票的权重和。
    # 避免"单路命中"时加权分被人为压低（如 0.3*0.9=0.27），
    # 导致永远达不到高置信阈值。
    weight_by_intent: dict[L0Intent, float] = {}
    if llm_decision is not None:
        weight_by_intent[llm_decision.intent] = config.weight_llm
    if vector_match is not None:
        weight_by_intent[vector_match.intent] = (
            weight_by_intent.get(vector_match.intent, 0.0)
            + config.weight_vector
        )
    normalized: dict[L0Intent, float] = {}
    for intent, score in scores.items():
        weight = weight_by_intent.get(intent, 0.0)
        normalized[intent] = score / weight if weight > 0 else 0.0

    ranked = sorted(
        normalized.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    top_intent, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    router_source = source_by_intent.get(top_intent, "fallback")
    router_path = f"fusion:{router_source}"
    # TOOL / CLARIFY：语义明确，直接采用（保持 LLM 的工具信息）。
    if top_intent in (L0Intent.TOOL, L0Intent.CLARIFY):
        return _build(
            intent=top_intent,
            domain=domain_by_intent.get(
                top_intent, IntentDomain.GENERAL
            ),
            confidence=top_score,
            router_path=router_path,
            reason=(
                    llm_reason
                    or "融合投票命中 TOOL/CLARIFY，语义明确。"
            ),
            tool=llm_tool.get(top_intent),
            source_scores=source_scores,
        )
    # 双路分歧：最高分与次高分差距过小 → 按默认降级。
    if len(ranked) > 1 and top_score - second_score < config.conf_gap:
        return _fallback(
            config=config,
            confidence=top_score,
            reason="意图识别两路分歧，按默认策略降级。",
            source_scores=source_scores,
        )
        # 置信度分级。
    if top_score >= config.conf_high:
        return _build(
            intent=top_intent,
            domain=domain_by_intent.get(
                top_intent, IntentDomain.GENERAL
            ),
            confidence=top_score,
            router_path=router_path,
            reason=(
                    llm_reason
                    or f"融合投票命中 {top_intent.value}。"
            ),
            tool=llm_tool.get(top_intent),
            source_scores=source_scores,
        )

    if top_score >= config.conf_low:
        # 中等置信：CHAT 降级为默认检索防漏检，其余照常采用。
        if top_intent == L0Intent.CHAT:
            return _fallback(
                config=config,
                confidence=top_score,
                reason="CHAT 置信度中等，按 RAG 优先降级防漏检。",
                source_scores=source_scores,
            )
        return _build(
            intent=top_intent,
            domain=domain_by_intent.get(
                top_intent, IntentDomain.GENERAL
            ),
            confidence=top_score,
            router_path=router_path,
            reason=(
                    llm_reason
                    or f"融合投票命中 {top_intent.value}（中等置信）。"
            ),
            tool=llm_tool.get(top_intent),
            source_scores=source_scores,
        )

        # 低置信 → 按配置默认。
    return _fallback(
        config=config,
        confidence=top_score,
        reason="意图置信度低，按默认策略降级。",
        source_scores=source_scores,
    )
def _build(
    intent: L0Intent,
    domain: IntentDomain,
    confidence: float,
    router_path: str,
    reason: str,
    source_scores: dict[str, float],
    tool=None,
) -> RouteDecision:
    """按意图构建 RouteDecision。"""
    return RouteDecision(
        intent=intent,
        need_rag=intent == L0Intent.KNOWLEDGE,
        confidence=confidence,
        reason=reason,
        domain=domain,
        tool=tool,
        router_path=router_path,
        source_scores=source_scores,
        intent_confidence=confidence,
    )


def _fallback(
    config: FusionConfig,
    confidence: float,
    reason: str,
    source_scores: dict[str, float],
) -> RouteDecision:
    """低置信/分歧兜底：默认 RAG 优先，可按配置改为 chat / clarify。"""
    default = config.default_on_low_confidence
    if default == "chat":
        return _build(
            L0Intent.CHAT,
            IntentDomain.GENERAL,
            confidence,
            "fusion:fallback",
            reason,
            source_scores,
        )
    if default == "clarify":
        return _build(
            L0Intent.CLARIFY,
            IntentDomain.GENERAL,
            confidence,
            "fusion:fallback",
            reason,
            source_scores,
        )
    return _build(
        L0Intent.KNOWLEDGE,
        IntentDomain.GENERAL,
        confidence,
        "fusion:fallback",
        reason,
        source_scores,
    )



