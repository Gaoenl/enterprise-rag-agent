"""Request and response schemas for the basic chat API."""
from typing import Any

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.answer_schema import AnswerStatus
from app.rag.schemas.routing_schema import RouteDecision
from app.schemas.trace_schema import TokenUsage, RagTraceData


class ChatHistoryMessage(BaseModel):
    """One historical chat message."""

    role: str = Field(..., description="Message role: USER or ASSISTANT.")
    content: str = Field(..., description="Message content.")


class ChatRequest(BaseModel):
    """Java 网关传入的最小聊天命令。"""

    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )
    conversation_id: int | None = Field(
        default=None,
        alias="conversationId",
    )
    tenant_id: int = Field(
        ...,
        alias="tenantId",
    )
    user_id: int = Field(
        ...,
        alias="userId",
    )
    knowledge_base_id: int | None = Field(
        default=None,
        alias="knowledgeBaseId",
    )
    trace_id: int = Field(
        ...,
        alias="traceId",
    )
    request_id: str = Field(
        ...,
        alias="requestId",
    )
    model: str | None = None




class ChatData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: int = Field(alias="conversationId")
    trace_id: int = Field(alias="traceId")
    question: str
    standalone_query: str = Field(alias="standaloneQuery")
    answer: str
    model: str
    mode: str
    intent: str
    route: RouteDecision | None = None
    need_rag: bool = Field(alias="needRag")
    knowledge_base_id: int | None = Field(
        default=None,
        alias="knowledgeBaseId",
    )
    route_reason: str | None = Field(
        default=None,
        alias="routeReason",
    )
    citations: list[dict[str, Any]] = Field(
        default_factory=list,
    )
    answer_status: AnswerStatus = Field(alias="answerStatus")
    used_citation_indexes: list[int] = Field(
        default_factory=list,
        alias="usedCitationIndexes",
    )
    invalid_citation_indexes: list[int] = Field(
        default_factory=list,
        alias="invalidCitationIndexes",
    )
    token_usage: TokenUsage = Field(
        default_factory=TokenUsage,
        alias="tokenUsage",
    )
    trace: RagTraceData | None = None
class LlmResult(BaseModel):
    """LLM Client 的统一返回结果。"""

    answer: str
    model: str = ""
    token_usage: TokenUsage = Field(
        default_factory=TokenUsage,
    )
