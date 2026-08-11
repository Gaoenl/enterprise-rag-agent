"""检索调试接口请求与响应模型。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    """允许 Java 使用 camelCase、Python 使用 snake_case。"""

    model_config = ConfigDict(populate_by_name=True)


class RetrievalMode(str, Enum):
    """检索模式。"""

    VECTOR = "VECTOR"
    KEYWORD = "KEYWORD"
    HYBRID = "HYBRID"


class RetrievalDebugRequest(CamelModel):
    """Java 调用 Python 时传入的检索调试参数。"""

    request_id: str | None = Field(None, alias="requestId", description="请求链路 ID。")
    tenant_id: int = Field(..., alias="tenantId", description="当前租户 ID。")
    user_id: int = Field(..., alias="userId", description="当前用户 ID。")
    knowledge_base_id: int | None = Field(
        None,
        alias="knowledgeBaseId",
        description="知识库 ID；不传则在当前租户全部知识库范围内检索。",
    )
    question: str = Field(..., min_length=1, max_length=4000, description="原始问题。")
    mode: RetrievalMode = Field(default=RetrievalMode.HYBRID, description="检索模式。")
    enable_rewrite: bool = Field(default=True, alias="enableRewrite")
    enable_rerank: bool = Field(default=True, alias="enableRerank")
    enable_multi_query: bool = Field(
        default=True,
        alias="enableMultiQuery",
        description="是否启用多查询召回（宽泛问题拆子查询）。",
    )
    vector_top_k: int | None = Field(None, alias="vectorTopK", ge=1, le=100)
    keyword_top_k: int | None = Field(None, alias="keywordTopK", ge=1, le=100)
    fusion_top_k: int | None = Field(None, alias="fusionTopK", ge=1, le=100)
    final_top_k: int | None = Field(None, alias="finalTopK", ge=1, le=50)
    rrf_k: int | None = Field(None, alias="rrfK", ge=1, le=1000)
    vector_weight: float | None = Field(None, alias="vectorWeight", ge=0, le=10)
    keyword_weight: float | None = Field(None, alias="keywordWeight", ge=0, le=10)


class RetrievalCandidateData(CamelModel):
    """某一个检索阶段的候选分片。"""

    chunk_id: int = Field(..., alias="chunkId")
    document_id: int = Field(..., alias="documentId")
    knowledge_base_id: int = Field(..., alias="knowledgeBaseId")
    chunk_index: int = Field(..., alias="chunkIndex")
    document_name: str | None = Field(None, alias="documentName")
    content: str
    vector_score: float | None = Field(None, alias="vectorScore")
    keyword_score: float | None = Field(None, alias="keywordScore")
    fusion_score: float | None = Field(None, alias="fusionScore")
    rerank_score: float | None = Field(None, alias="rerankScore")
    vector_rank: int | None = Field(None, alias="vectorRank")
    keyword_rank: int | None = Field(None, alias="keywordRank")
    fusion_rank: int | None = Field(None, alias="fusionRank")
    rerank_rank: int | None = Field(None, alias="rerankRank")
    retrieval_sources: list[str] = Field(default_factory=list, alias="retrievalSources")
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation_index: int | None = Field(None, alias="citationIndex")
    context_truncated: bool = Field(False, alias="contextTruncated")


class PackedContextData(CamelModel):
    """最终送入 LLM 前的上下文打包结果。"""

    text: str = ""
    total_chars: int = Field(default=0, alias="totalChars")
    truncated: bool = False
    documents: list[RetrievalCandidateData] = Field(default_factory=list)


class RetrievalTimingData(CamelModel):
    """各阶段执行耗时，单位为毫秒。"""

    rewrite_millis: int = Field(default=0, alias="rewriteMillis")
    vector_millis: int = Field(default=0, alias="vectorMillis")
    keyword_millis: int = Field(default=0, alias="keywordMillis")
    fusion_millis: int = Field(default=0, alias="fusionMillis")
    rerank_millis: int = Field(default=0, alias="rerankMillis")
    packing_millis: int = Field(default=0, alias="packingMillis")
    total_millis: int = Field(default=0, alias="totalMillis")


class RetrievalConfigData(CamelModel):
    """检索调试默认参数（来自 Python 服务端配置），供前端初始化表单。"""

    vector_top_k: int = Field(alias="vectorTopK")
    keyword_top_k: int = Field(alias="keywordTopK")
    fusion_top_k: int = Field(alias="fusionTopK")
    final_top_k: int = Field(alias="finalTopK")
    rrf_k: int = Field(alias="rrfK")
    vector_weight: float = Field(alias="vectorWeight")
    keyword_weight: float = Field(alias="keywordWeight")
    multi_query_enabled: bool = Field(alias="multiQueryEnabled")
    multi_query_top_k: int = Field(alias="multiQueryTopK")
    synonym_expansion_enabled: bool = Field(
        alias="synonymExpansionEnabled"
    )


class RetrievalDebugData(CamelModel):
    """检索调试接口完整响应数据。"""

    original_query: str = Field(..., alias="originalQuery")
    semantic_query: str = Field(..., alias="semanticQuery")
    keywords: list[str] = Field(default_factory=list)
    alternative_queries: list[str] = Field(
        default_factory=list,
        alias="alternativeQueries",
        description="多查询召回的子查询列表。",
    )
    vector_merged_count: int = Field(
        default=0,
        alias="vectorMergedCount",
        description="多路向量候选合并去重后的数量。",
    )
    mode: RetrievalMode
    rewrite_applied: bool = Field(False, alias="rewriteApplied")
    rerank_applied: bool = Field(False, alias="rerankApplied")
    degraded: bool = False
    vector_results: list[RetrievalCandidateData] = Field(default_factory=list, alias="vectorResults")
    keyword_results: list[RetrievalCandidateData] = Field(default_factory=list, alias="keywordResults")
    fusion_results: list[RetrievalCandidateData] = Field(default_factory=list, alias="fusionResults")
    rerank_results: list[RetrievalCandidateData] = Field(default_factory=list, alias="rerankResults")
    packed_context: PackedContextData = Field(default_factory=PackedContextData, alias="packedContext")
    timings: RetrievalTimingData = Field(default_factory=RetrievalTimingData)
    warnings: list[str] = Field(default_factory=list)
