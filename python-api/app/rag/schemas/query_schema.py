"""RAG 工作流对外使用的查询、准备结果和最终结果模型。"""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document

from app.rag.schemas.routing_schema import RouteDecision
from app.schemas.chat_schema import ChatHistoryMessage
from app.schemas.trace_schema import TokenUsage
from app.schemas.answer_schema import AnswerStatus


@dataclass
class RagQuery:
    """面向业务层的 RAG 请求。"""

    question: str
    history: list[ChatHistoryMessage] = field(default_factory=list)
    summary: str | None = None
    tenant_id: int | None = None
    user_id: int | None = None
    knowledge_base_id: int | None = None
    model: str | None = None
    last_route: RouteDecision | None = None
    tool_enabled: bool = True


@dataclass
class RagPrepared:
    """LLM 生成前已经确定的查询、上下文和引用信息。"""

    question: str
    standalone_query: str
    model: str
    history: list[ChatHistoryMessage]
    intent: str
    need_rag: bool
    knowledge_base_id: int | None = None
    route: RouteDecision | None = None
    route_reason: str | None = None
    context: str = ""
    documents: list[Document] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    candidate_count: int = 0
    rerank_count: int = 0
    context_document_count: int = 0
    no_evidence: bool = False
    clarification_answer: str | None = None
    tool_result: str = ""


@dataclass
class RagResult:
    """一次完整 RAG 问答的结果。"""

    answer: str
    answer_status: AnswerStatus
    intent: str
    need_rag: bool
    standalone_query: str = ""
    model: str = ""
    knowledge_base_id: int | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    route: RouteDecision | None = None
    route_reason: str | None = None
