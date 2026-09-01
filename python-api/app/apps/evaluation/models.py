"""RAG 离线测评数据模型。"""

from enum import Enum

from pydantic import BaseModel, Field


class EvaluationTaskType(str, Enum):
    """当前支持的测评任务类型。"""

    QUESTANSWER_1DOC = "QUESTANSWER_1DOC"


class EvaluationCase(BaseModel):
    """一条问题、标准答案和金标准文档的对应关系。"""

    case_id: str = Field(..., description="项目内部唯一测试用例编号。")
    source_record_id: str = Field(..., description="CRUD-RAG 原始 ID。")
    source_index: int = Field(..., ge=0, description="原始数组中的位置。")

    question: str = Field(..., min_length=1, description="测试问题。")
    reference_answer: str = Field(
        ...,
        min_length=1,
        description="CRUD-RAG 提供的标准答案。",
    )

    gold_document_keys: list[str] = Field(
        ...,
        min_length=1,
        description="回答该问题所需的金标准文档标识。",
    )

    # 可选的答案证据文本。只有数据集明确标注证据时，才计算分块级指标。
    gold_evidence_texts: list[str] = Field(
        default_factory=list,
        description="能够直接支持标准答案的原文片段。",
    )

    dataset: str = Field(default="CRUD-RAG")
    task_type: EvaluationTaskType = Field(
        default=EvaluationTaskType.QUESTANSWER_1DOC
    )


class CorpusDocument(BaseModel):
    """导入测评知识库的一篇独立文档。"""

    document_key: str = Field(..., description="稳定的文档业务标识。")
    file_name: str = Field(..., description="生成的 TXT 文件名。")
    relative_path: str = Field(..., description="相对测评数据目录的路径。")
    sha256: str = Field(..., description="文档内容摘要。")

    is_gold: bool = Field(
        ...,
        description="是否为某个测试问题的金标准文档。",
    )
    case_id: str | None = Field(
        default=None,
        description="金标准文档对应的测试用例。",
    )

    source_part: str = Field(
        ...,
        description="原始数据文件或数据集节点。",
    )
    source_line: int | None = Field(
        default=None,
        ge=1,
        description="文档在 part 文件中的行号。",
    )


class PreparedDatasetSummary(BaseModel):
    """数据转换完成后的统计摘要。"""

    dataset: str = "CRUD-RAG"
    task_type: EvaluationTaskType
    random_seed: int

    case_count: int = Field(..., ge=1)
    gold_document_count: int = Field(..., ge=1)
    negative_document_count: int = Field(..., ge=0)
    hard_negative_document_count: int = Field(default=0, ge=0)
    total_document_count: int = Field(..., ge=1)
