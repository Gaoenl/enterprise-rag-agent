"""LangGraph 节点使用的依赖接口。

工作流节点只依赖这里声明的能力，不直接访问 RagEngine 的私有属性。
生产实现由 runner.py 注入，测试则可以注入轻量 fake。
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

from app.rag.retriever.hybrid_retriever import RetrievalStats
from app.rag.schemas.context_schema import PackedContext
from app.rag.schemas.query_schema import RagQuery
from app.rag.schemas.routing_schema import (
    KnowledgeBaseSelection,
    ResolvedQuery,
    RetrievalQuery,
    RouteDecision,
)
from app.rag.settings import RagSettings
from app.rag.trace.trace_recorder import TraceRecorder

TraceNode = Callable[
    [str, dict[str, Any] | None, TraceRecorder | None],
    AbstractContextManager[Any],
]
ResolveQuery = Callable[[RagQuery], ResolvedQuery]
RouteIntent = Callable[[RagQuery, ResolvedQuery], RouteDecision]
SkipRetrieval = Callable[[TraceRecorder | None, str], None]
SelectKnowledgeBase = Callable[..., KnowledgeBaseSelection]
RewriteRetrievalQuery = Callable[[str], RetrievalQuery]
RetrieveDocuments = Callable[
    ...,
    tuple[list[Document], RetrievalStats],
]
RerankDocuments = Callable[[str, list[Document]], list[Document]]
PackDocuments = Callable[[list[Document]], PackedContext]
BuildCitations = Callable[[list[Document]], list[dict[str, Any]]]
BuildClarification = Callable[[KnowledgeBaseSelection], str]
IsToolRegistered = Callable[[str], bool]
ExecuteTool = Callable[[str, dict[str, Any]], str]


@dataclass(frozen=True)
class RoutingDependencies:
    """查询解析和分支准备所需的能力。"""

    settings: RagSettings
    trace_node: TraceNode
    resolve_query: ResolveQuery
    route_intent: RouteIntent
    skip_retrieval_stage: SkipRetrieval


@dataclass(frozen=True)
class RetrievalDependencies:
    """知识库检索链路所需的能力。"""

    settings: RagSettings
    trace_node: TraceNode
    select_knowledge_base: SelectKnowledgeBase
    rewrite_retrieval_query: RewriteRetrievalQuery
    retrieve_documents: RetrieveDocuments
    rerank_documents: RerankDocuments
    pack_documents: PackDocuments
    build_citations: BuildCitations
    build_clarification_answer: BuildClarification


@dataclass(frozen=True)
class ToolDependencies:
    """工具校验和执行所需的能力。"""

    settings: RagSettings
    trace_node: TraceNode
    is_tool_registered: IsToolRegistered
    execute_tool: ExecuteTool


@dataclass(frozen=True)
class RagWorkflowDependencies:
    """RAG 工作流的完整依赖集合。"""

    routing: RoutingDependencies
    retrieval: RetrievalDependencies
    tool: ToolDependencies
