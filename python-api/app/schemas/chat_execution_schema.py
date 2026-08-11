"""聊天流程内部使用的数据对象。"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chat_schema import ChatHistoryMessage
from app.schemas.trace_schema import TokenUsage


class ChatExecutionContext(BaseModel):
    """完成路由、检索和上下文组装后的执行数据。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    question: str
    standalone_query: str
    model: str

    intent: str
    need_rag: bool
    route_reason: str | None = None
    knowledge_base_id: int | None = None

    history: list[ChatHistoryMessage] = Field(default_factory=list)
    context: str = ""
    documents: list = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)

    no_evidence: bool = False
    clarification_answer: str | None = None

    tool_result: str = ""