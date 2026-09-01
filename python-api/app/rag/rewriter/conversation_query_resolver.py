"""结合会话历史，将当前追问改写为独立问题。"""
import re

from langchain_core.prompts import ChatPromptTemplate

from app.schemas.chat_schema import ChatHistoryMessage
from app.rag.schemas.routing_schema import ResolvedQuery


class ConversationQueryResolver:
    """多轮会话问题独立化处理器。"""

    # 出现这些表达时，当前问题通常依赖上一轮上下文。
    _REFERENCE_PATTERN = re.compile(
        r"(它|他|她|这个|那个|这些|那些|上述|上面|前面|"
        r"刚才|其中|继续|详细说|第二点|第三点|具体呢)"
    )
    def __init__(self, chat_model) -> None:
        """接收已经初始化完成的 LangChain ChatModel。"""
        self._chat_model = chat_model

        # Prompt 只要求改写，不允许回答问题。
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你负责将多轮对话中的当前问题改写为可独立理解的问题。\n"
                    "要求：\n"
                    "1. 只补全当前问题缺少的对象和上下文；\n"
                    "2. 不回答问题；\n"
                    "3. 不增加对话中不存在的事实；\n"
                    "4. 当前问题已经完整时原样返回；\n"
                    "5. 只输出改写后的问题。",
                ),
                (
                    "human",
                    "对话历史：\n{history}\n\n当前问题：\n{question}",
                ),
            ]
        )
        # LangChain LCEL：Prompt 的输出直接传给模型。
        self._chain = self._prompt | self._chat_model

    def resolve(
            self,
            question: str,
            history: list[ChatHistoryMessage],
    ) -> ResolvedQuery:
        """根据历史将当前问题转换为独立问题。"""
        normalized_question = question.strip()

        # 没有历史时，当前问题不需要补全上下文。
        if not history:
            return ResolvedQuery(
                original_query=normalized_question,
                standalone_query=normalized_question,
                rewritten=False,
                reason="当前会话没有历史消息。",
            )

        # 问题没有明显的上下文依赖特征时，跳过模型调用。
        if not self._should_rewrite(normalized_question):
            return ResolvedQuery(
                original_query=normalized_question,
                standalone_query=normalized_question,
                rewritten=False,
                reason="当前问题可以独立理解。",
            )

        # 只保留最近若干条历史，避免 Prompt 无限增长。
        history_text = self._format_history(history[-8:])

        try:
            # 调用 LangChain Chain 执行问题改写。
            response = self._chain.invoke(
                {
                    "history": history_text,
                    "question": normalized_question,
                }
            )

            # 不同模型可能返回字符串或多内容结构，这里统一转换。
            rewritten_query = (
                response.content
                if isinstance(response.content, str)
                else str(response.content)
            ).strip()

            # 模型返回空内容时使用原始问题降级。
            if not rewritten_query:
                return self._fallback(normalized_question, "模型返回了空改写结果。")

            return ResolvedQuery(
                original_query=normalized_question,
                standalone_query=rewritten_query,
                rewritten=rewritten_query != normalized_question,
                reason="检测到当前问题依赖会话历史。",
            )
        except Exception:
            # 问题改写失败不应导致整个聊天接口失败。
            return self._fallback(normalized_question, "问题改写模型调用失败。")

    def _should_rewrite(self, question: str) -> bool:
        """判断当前问题是否可能依赖会话上下文。"""
        if self._REFERENCE_PATTERN.search(question):
            return True

        # 非常短的追问通常没有完整主语。
        return len(question) <= 10
    @staticmethod
    def _format_history(history: list[ChatHistoryMessage]) -> str:
        """将历史消息转换为适合写入 Prompt 的文本。"""
        lines: list[str] = []

        for item in history:
            role_name = "用户" if item.role == "USER" else "助手"
            lines.append(f"{role_name}：{item.content}")

        return "\n".join(lines)

    @staticmethod
    def _fallback(question: str, reason: str) -> ResolvedQuery:
        """改写失败时使用原始问题继续流程。"""
        return ResolvedQuery(
            original_query=question,
            standalone_query=question,
            rewritten=False,
            reason=reason,
        )