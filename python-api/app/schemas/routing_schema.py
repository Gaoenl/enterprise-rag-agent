from enum import Enum

from pydantic import BaseModel, Field
"""问题改写、意图路由和知识库选择使用的数据模型。"""

class L0Intent(str, Enum):
    """L0 路由决策层的四类意图。"""

    CHAT = "CHAT"                # 普通对话：不检索、不调工具
    KNOWLEDGE = "KNOWLEDGE"      # 知识检索：进入 RAG 链路
    TOOL = "TOOL"                # 工具调用：执行外部工具
    CLARIFY = "CLARIFY"          # 引导澄清：信息不足，引导补充
class IntentDomain(str, Enum):
    """L1 业务域，用于知识库路由。"""

    EXPENSE = "EXPENSE"
    HR = "HR"
    CONTRACT = "CONTRACT"
    POLICY = "POLICY"
    GENERAL = "GENERAL"

class ToolRequest(BaseModel):
    """TOOL 意图的工具调用请求。"""

    tool: str = Field(..., description="工具名，如 calculator / web_search")
    tool_input: dict = Field(default_factory=dict, description="工具入参")
class ResolvedQuery(BaseModel):
    """多轮问题独立化结果。"""

    original_query: str = Field(..., description="用户输入的原始问题。")
    standalone_query: str = Field(..., description="脱离历史也能理解的完整问题。")
    rewritten: bool = Field(default=False, description="是否发生了问题改写。")
    reason: str | None = Field(default=None, description="执行或跳过改写的原因。")
class RouteDecision(BaseModel):
    """意图路由结果。"""
    """L0 路由决策结果。"""
    intent: L0Intent
    need_rag: bool
    confidence: float
    reason: str
    domain: IntentDomain = IntentDomain.GENERAL
    tool: ToolRequest | None = None
    router_path: str = "rule"  # rule / vector / llm / fallback / inherit
    inherit_context: bool = False  # True 表示直接继承上一轮决策
class KnowledgeBaseCandidate(BaseModel):
    """用户当前可用的知识库候选项。"""

    id: int = Field(..., description="知识库 ID。")
    name: str = Field(..., description="知识库名称。")
    description: str | None = Field(default=None, description="知识库描述。")
class KnowledgeBaseSelection(BaseModel):
    """知识库选择结果。"""

    knowledge_base_id: int | None = Field(default=None, description="最终选择的知识库 ID。")
    selection_type: str = Field(..., description="知识库选择方式。")
    confidence: float = Field(default=1.0, ge=0, le=1, description="选择置信度。")
    need_clarification: bool = Field(default=False, description="是否需要用户选择知识库。")
    reason: str = Field(..., description="选择依据。")
    candidates: list[KnowledgeBaseCandidate] = Field(
        default_factory=list,
        description="需要用户选择时返回的候选知识库。",
    )
class RetrievalQuery(BaseModel):
    """面向混合检索优化后的查询。"""

    semantic_query: str = Field(
        ...,
        description="用于生成 Embedding 和向量检索的语义查询。",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="用于 PostgreSQL 精确关键词检索的关键词。",
    )
    alternative_queries: list[str] = Field(
        default_factory=list,
        description="后续多查询召回使用的扩展问题。",
    )