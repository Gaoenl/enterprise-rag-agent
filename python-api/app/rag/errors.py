"""RAG 核心库统一异常体系。

核心库不依赖 FastAPI，不抛 HTTPException；HTTP 状态码由 api 层
根据异常类型统一转换。
"""


class RagError(Exception):
    """RAG 核心统一异常基类。"""


class ConfigurationError(RagError):
    """配置缺失或非法。"""


class EmbeddingError(RagError):
    """Embedding 模型调用失败。"""


class LLMError(RagError):
    """LLM 调用失败。"""


class RetrievalError(RagError):
    """检索失败（含降级后仍失败）。"""


class IntentError(RagError):
    """意图识别失败。"""


class InvalidQueryError(RagError):
    """查询参数校验失败。"""
