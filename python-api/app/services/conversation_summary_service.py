from langchain_core.prompts import ChatPromptTemplate

from app.core.chat_model_factory import get_chat_model
from app.schemas.conversation_summary_schema import SummarizeRequest

SYSTEM_PROMPT = (
    "你是会话摘要助手。用 2-3 句话总结对话的关键信息，"
    "保留日期、金额、结论、待办等事实；"
    "若提供旧摘要，将新增对话合并进旧摘要而非重写整段；"
    "只输出摘要，不要其他内容。"
)


class ConversationSummaryService:
    def __init__(self) -> None:
        self._chain = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "旧摘要：\n{old_summary}\n\n新增对话：\n{messages}\n\n摘要："),
            ]
        ) | get_chat_model()

    def summarize(self, request: SummarizeRequest) -> str:
        messages_text = "\n".join(
            f"{m.role}: {m.content}" for m in request.messages
        )
        response = self._chain.invoke(
            {
                "old_summary": request.old_summary or "无",
                "messages": messages_text,
            }
        )
        content = response.content
        return content.strip() if isinstance(content, str) else str(content).strip()