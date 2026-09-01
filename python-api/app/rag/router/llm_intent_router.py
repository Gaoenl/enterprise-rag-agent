"""LLM 慢路径意图路由：few-shot + 结构化 JSON 输出。

仅当规则与向量快路径置信度不足时调用；解析失败或异常返回 None，
由 IntentRouter 统一兜底，不影响主流程。
"""

import json
import re

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.rag.llm.chat_model_factory import get_chat_model
from app.rag.schemas.routing_schema import (
    IntentDomain,
    L0Intent,
    RouteDecision,
    ToolRequest,
)

SYSTEM_PROMPT = """你是企业问答系统的意图路由器。请判断用户问题属于哪一类意图，并输出 JSON。

意图四分类：
1. CHAT      普通对话：问候、闲聊、自我介绍等，不需要检索知识库，也不需要调用工具。
2. KNOWLEDGE 知识检索：询问公司制度、报销、人事、合同等企业内部信息，需要检索知识库。
3. TOOL      工具调用：需要实时信息或计算的请求（如天气、日期、数学计算）。
4. CLARIFY   引导澄清：问题为空、含糊不清或缺少必要信息。

业务域（仅 KNOWLEDGE 需要）：
- EXPENSE 报销  HR 人事  CONTRACT 合同  POLICY 制度  GENERAL 其他/未分类

输出必须是合法 JSON，禁止输出 JSON 以外的内容。格式：
{"intent":"CHAT|KNOWLEDGE|TOOL|CLARIFY","domain":"EXPENSE|HR|CONTRACT|POLICY|GENERAL","confidence":0.0到1.0,"reason":"简短理由"}

TOOL 意图额外输出：
{"intent":"TOOL","tool":"calculator|web_search","tool_input":{...},"confidence":0.0到1.0,"reason":"..."}

示例：
问题：公司的报销标准是什么
输出：{"intent":"KNOWLEDGE","domain":"EXPENSE","confidence":0.95,"reason":"询问报销标准"}

问题：你好
输出：{"intent":"CHAT","domain":"GENERAL","confidence":0.99,"reason":"问候语"}

问题：计算 2 的 10 次方
输出：{"intent":"TOOL","tool":"calculator","tool_input":{"expression":"2**10"},"confidence":0.97,"reason":"数学计算"}
"""


class LlmIntentRouter:
    """基于 LangChain 聊天模型的结构化意图分类器。"""

    def __init__(self) -> None:
        self._chat_model = get_chat_model()
        self._prompt = ChatPromptTemplate.from_messages(
            [
                # SYSTEM_PROMPT 含 JSON 示例大括号，直接传消息对象避免 f-string 解析。
                SystemMessage(content=SYSTEM_PROMPT),
                ("human", "问题：{question}\n输出："),
            ]
        )
        self._chain = self._prompt | self._chat_model

    def classify(self, query: str) -> RouteDecision | None:
        """分类并返回 RouteDecision；任何异常返回 None 交给上层兜底。"""
        try:
            response = self._chain.invoke({"question": query.strip()})
            content = response.content
            if not isinstance(content, str):
                content = str(content)
            payload = self._parse_json(content)
            if payload is None:
                return None

            intent = self._parse_intent(payload)
            if intent is None:
                return None

            domain = self._parse_domain(payload, intent)
            confidence = self._parse_confidence(payload)

            tool = None
            if intent == L0Intent.TOOL:
                tool_name = str(payload.get("tool") or "").strip()
                if tool_name:
                    tool = ToolRequest(
                        tool=tool_name,
                        tool_input=dict(payload.get("tool_input") or {}),
                    )
                else:
                    # TOOL 意图缺少工具名，无法执行，按澄清处理。
                    return RouteDecision(
                        intent=L0Intent.CLARIFY,
                        need_rag=False,
                        confidence=confidence,
                        router_path="llm",
                        reason="LLM 判定为工具调用但未提供工具名，引导澄清。",
                    )

            reason = str(payload.get("reason") or "LLM 结构化路由。")
            return RouteDecision(
                intent=intent,
                need_rag=intent == L0Intent.KNOWLEDGE,
                confidence=confidence,
                reason=reason,
                domain=domain,
                tool=tool,
                router_path="llm",
            )
        except Exception:
            # 慢路径失败不中断主流程，交给 IntentRouter 兜底。
            return None

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        """从模型输出中提取 JSON 对象；兼容 markdown 代码块与前后杂文。"""
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match is None:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _parse_intent(payload: dict) -> L0Intent | None:
        intent = str(payload.get("intent") or "").strip().upper()
        try:
            return L0Intent(intent)
        except ValueError:
            return None

    @staticmethod
    def _parse_domain(payload: dict, intent: L0Intent) -> IntentDomain:
        domain = str(payload.get("domain") or "").strip().upper()
        try:
            return IntentDomain(domain)
        except ValueError:
            # 非法域回退 GENERAL；非 KNOWLEDGE 意图域不参与路由。
            return IntentDomain.GENERAL

    @staticmethod
    def _parse_confidence(payload: dict) -> float:
        try:
            value = float(payload.get("confidence"))
            return max(0.0, min(1.0, value))
        except (TypeError, ValueError):
            return 0.0