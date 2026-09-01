"""混合检索过程中使用的数据模型。"""

from pydantic import BaseModel, Field


class RetrievalCandidate(BaseModel):
    """向量检索或关键词检索返回的候选分片。"""

    chunk_id: int = Field(..., description="文档分片 ID。")
    document_id: int = Field(..., description="所属文档 ID。")
    knowledge_base_id: int = Field(..., description="所属知识库 ID。")
    chunk_index: int = Field(..., description="分片在文档中的顺序。")
    content: str = Field(..., description="分片文本内容。")
    document_name: str | None = Field(default=None, description="文档名称。")

    vector_score: float | None = Field(
        default=None,
        description="向量检索的余弦相似度。",
    )
    embedding_model: str | None = Field(
        default=None,
        description="生成该向量使用的模型。",
    )
    embedding_dimension: int | None = Field(
        default=None,
        description="生成该向量使用的维度。",
    )
    keyword_score: float | None = Field(
        default=None,
        description="关键词检索的命中分数。",
    )
    fusion_score: float = Field(
        default=0.0,
        description="RRF 融合分数。",
    )

    vector_rank: int | None = Field(
        default=None,
        description="候选分片在向量检索中的排名。",
    )
    keyword_rank: int | None = Field(
        default=None,
        description="候选分片在关键词检索中的排名。",
    )

    retrieval_sources: list[str] = Field(
        default_factory=list,
        description="召回来源，例如 vector、keyword。",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="文档分片原始 metadata。",
    )