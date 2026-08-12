"""Request and response schemas for the basic chat API."""
from typing import Any

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.answer_schema import AnswerStatus
from app.schemas.trace_schema import TokenUsage, RagTraceData


class ChatHistoryMessage(BaseModel):
    """One historical chat message."""

    role: str = Field(..., description="Message role: USER or ASSISTANT.")
    content: str = Field(..., description="Message content.")


class ChatRequest(BaseModel):
    """Request body for a user question.

    This first version does not run retrieval. It only sends the question
    directly to the configured chat model.
    """
    # 允许同时使用 snake_case 和 Java 发送的 camelCase。
    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(..., min_length=1, description="用户当前问题。")
    model: str | None = Field(default=None, description="本次使用的模型。")
    tenant_id: int | None = Field(default=None, alias="tenantId", description="租户 ID。")
    user_id: int | None = Field(default=None, alias="userId", description="用户 ID。")
    trace_id: int = Field(
        ...,
        alias="traceId",
        description="Java 生成的 RAG Trace ID。",
    )

    request_id: str | None = Field(
        default=None,
        alias="requestId",
        description="Java 与 Python 日志关联 ID。",
    )
    conversation_id: int | None = Field(
        default=None,
        alias="conversationId",
        description="会话 ID。",
    )
    knowledge_base_id: int | None = Field(
        default=None,
        alias="knowledgeBaseId",
        description="用户明确选择的知识库 ID。",
    )
    history: list[ChatHistoryMessage] = Field(
        default_factory=list,
        description="Java 查询出的正式会话历史。",
    )
    summary: str | None = Field(
        default=None,
        description="会话摘要（Java 侧压缩后），可空。",
    )


class ChatData(BaseModel):
    """聊天接口响应数据。"""

    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(..., description="用户原始问题。")
    standalone_query: str = Field(
        ...,
        alias="standaloneQuery",
        description="问题独立化结果。",
    )
    answer: str = Field(..., description="最终回答。")
    model: str = Field(..., description="实际使用的模型。")
    mode: str = Field(default="basic", description="回答模式。")
    intent: str = Field(..., description="识别出的用户意图。")
    need_rag: bool = Field(..., alias="needRag", description="是否执行了 RAG。")
    knowledge_base_id: int | None = Field(
        default=None,
        alias="knowledgeBaseId",
        description="实际查询的知识库 ID。",
    )
    route_reason: str | None = Field(
        default=None,
        alias="routeReason",
        description="路由决策原因。",
    )
    citations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="回答引用的文档分片。",
    )
    trace_id: int = Field(
        ...,
        alias="traceId",
    )

    answer_status: AnswerStatus = Field(
        ...,
        alias="answerStatus",
    )

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

    trace: RagTraceData | None = Field(
        default=None,
        description="开发阶段返回的完整 Trace。",
    )
class LlmResult(BaseModel):
    """LLM Client 的统一返回结果。"""

    answer: str
    model: str = ""
    token_usage: TokenUsage = Field(
        default_factory=TokenUsage,
    )
