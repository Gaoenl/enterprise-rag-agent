"""LangGraph 在节点之间传递的状态定义。

request 是初始输入；其他字段按流程执行顺序逐步写入。
"""

from typing import TypedDict

from langchain_core.documents import Document
from typing_extensions import NotRequired

from app.rag.schemas.context_schema import PackedContext
from app.rag.schemas.query_schema import RagPrepared, RagQuery
from app.rag.schemas.routing_schema import (
    KnowledgeBaseSelection,
    ResolvedQuery,
    RetrievalQuery,
    RouteDecision,
)


class RagState(TypedDict):
    """RAG 生成前工作流的共享状态。"""

    # 初始输入。
    request: RagQuery

    # 查询解析、路由和知识库选择阶段。
    resolved_query: NotRequired[ResolvedQuery]
    route_decision: NotRequired[RouteDecision]
    knowledge_base_selection: NotRequired[KnowledgeBaseSelection]

    # 检索、重排和上下文打包阶段。
    retrieval_query: NotRequired[RetrievalQuery]
    retrieved_documents: NotRequired[list[Document]]
    reranked_documents: NotRequired[list[Document]]
    packed_context: NotRequired[PackedContext]

    # 分支输出和最终准备结果。
    prepared: NotRequired[RagPrepared]
    clarification_answer: NotRequired[str]
    tool_result: NotRequired[str]
