"""RAG 检索测评 API 数据模型。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    """允许接口使用 camelCase、Python 内部使用 snake_case。"""

    model_config = ConfigDict(populate_by_name=True)


class EvaluationExperiment(str, Enum):
    """支持的检索实验。"""

    VECTOR = "VECTOR"
    KEYWORD = "KEYWORD"
    HYBRID = "HYBRID"
    HYBRID_RERANK = "HYBRID_RERANK"
    HYBRID_REWRITE = "HYBRID_REWRITE"
    HYBRID_REWRITE_RERANK = "HYBRID_REWRITE_RERANK"
    HYBRID_MULTI_QUERY = "HYBRID_MULTI_QUERY"
    HYBRID_MULTI_QUERY_REWRITE = "HYBRID_MULTI_QUERY_REWRITE"
    HYBRID_MULTI_QUERY_REWRITE_RERANK = (
        "HYBRID_MULTI_QUERY_REWRITE_RERANK"
    )


class EvaluationCreateRequest(CamelModel):
    """Java 创建评测任务时传入的可信参数。"""

    tenant_id: int = Field(..., alias="tenantId")
    user_id: int = Field(..., alias="userId")
    knowledge_base_id: int = Field(..., alias="knowledgeBaseId")
    dataset_code: str = Field(default="CRUD_RAG_V1", alias="datasetCode")
    experiments: list[EvaluationExperiment] = Field(min_length=1)
    vector_weight: float = Field(default=1.0, alias="vectorWeight", ge=0, le=10)
    keyword_weight: float = Field(default=1.0, alias="keywordWeight", ge=0, le=10)


class EvaluationRunData(CamelModel):
    """评测任务状态。"""

    run_id: str = Field(..., alias="runId")
    status: str
    dataset_code: str = Field(..., alias="datasetCode")
    knowledge_base_id: int = Field(..., alias="knowledgeBaseId")
    total_cases: int = Field(..., alias="totalCases")
    completed_cases: int = Field(..., alias="completedCases")
    progress: int
    current_experiment: str | None = Field(None, alias="currentExperiment")
    error_message: str | None = Field(None, alias="errorMessage")
    created_at: str = Field(..., alias="createdAt")
    finished_at: str | None = Field(None, alias="finishedAt")


class EvaluationResultData(CamelModel):
    """评测汇总和 Case 明细。"""

    run_id: str = Field(..., alias="runId")
    status: str
    summaries: list[dict[str, Any]] = Field(default_factory=list)
    details: list[dict[str, Any]] = Field(default_factory=list)
