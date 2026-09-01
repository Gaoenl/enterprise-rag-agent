"""上下文打包结果的数据模型。"""

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field


class PackedContext(BaseModel):
    """ContextPacker 的打包结果。"""

    # 允许 Pydantic 保存 LangChain Document。
    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = Field(
        default="",
        description="最终发送给 LLM 的知识库上下文文本。",
    )

    documents: list[Document] = Field(
        default_factory=list,
        description="实际进入上下文的文档分片。",
    )

    total_chars: int = Field(
        default=0,
        ge=0,
        description="最终上下文字符数量。",
    )

    truncated: bool = Field(
        default=False,
        description="是否因为长度限制截断或丢弃了部分内容。",
    )