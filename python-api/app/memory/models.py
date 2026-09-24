from dataclasses import dataclass

from app.rag.schemas.routing_schema import RouteDecision
from app.schemas.chat_schema import ChatHistoryMessage
from app.schemas.trace_schema import RagTraceData


@dataclass
class ConversationContext:
    tenant_id: int
    user_id: int
    conversation_id: int
    user_message_id: int
    trace_id: int

    history: list[ChatHistoryMessage]
    summary: str
    last_route: RouteDecision | None

    trace: RagTraceData