"""Rerank API 使用的数据模型。"""

from pydantic import BaseModel, Field


class RerankResultItem(BaseModel):
    """排序模型返回的单个结果。"""

    index: int = Field(
        ...,
        description="候选文档在原始 documents 数组中的位置。",
    )
    relevance_score: float = Field(
        ...,
        description="问题与候选文档的相关性分数。",
    )


class RerankResponse(BaseModel):
    """qwen3-rerank 接口响应。"""

    model: str = Field(..., description="实际使用的排序模型。")
    results: list[RerankResultItem] = Field(
        default_factory=list,
        description="排序后的候选结果。",
    )
    usage: dict = Field(
        default_factory=dict,
        description="模型 Token 用量。",
    )