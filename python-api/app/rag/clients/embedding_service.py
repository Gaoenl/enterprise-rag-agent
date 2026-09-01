"""Embedding business service.

这一层类似 Java 的 Service：
- 做业务参数校验。
- 选择默认模型。
- 调用 Client 层获取向量。
- 组装接口返回数据。
"""

from app.rag.errors import EmbeddingError, InvalidQueryError

from app.rag.clients.embedding_client import EmbeddingClient
from app.config import get_settings
from app.schemas.embedding_schema import EmbeddingData, EmbeddingItem, EmbeddingRequest


class EmbeddingService:
    """Service for creating text embeddings."""

    def __init__(self) -> None:
        # 读取全局配置。
        self._settings = get_settings()

        # Client 层负责真正生成或调用模型生成 Embedding。
        self._client = EmbeddingClient()

    def embed(self, request: EmbeddingRequest) -> EmbeddingData:
        """Create embeddings for all texts in the request."""
        # 先校验请求，避免空文本、超批量等无效请求进入模型层。
        self._validate_request(request)

        # 如果请求没有指定模型，就使用配置里的默认模型。
        model = request.model or self._settings.embedding_model
        # 调用 Client 层，当前版本会生成稳定 Mock 向量。
        vectors = self._client.embed_texts(request.texts, model)
        # 维度以模型实际返回为准（配置维度只做校验，不强制生成）。
        dimension = len(vectors[0]) if vectors else 0
        # enumerate 会同时拿到列表下标和元素。
        # index 用于告诉调用方：这个向量对应原始 texts 的第几个文本。

        items = [
            EmbeddingItem(index=index, embedding=vector)
            for index, vector in enumerate(vectors)
        ]

        return EmbeddingData(
            model=model,
            dimension=dimension,
            items=items,
        )

    def _validate_request(self, request: EmbeddingRequest) -> None:
        """Validate embedding request before calling the client."""
        # texts 不能为空。
        if not request.texts:
            raise InvalidQueryError("texts must not be empty")

        # 控制批量大小，避免一次请求塞太多文本导致模型调用过慢。
        if len(request.texts) > self._settings.embedding_batch_size:
            raise InvalidQueryError(f"texts size must be <= {self._settings.embedding_batch_size}",
            )

        # 每条文本都必须有实际内容。
        for index, text in enumerate(request.texts):
            if text is None or not text.strip():
                raise InvalidQueryError(f"texts[{index}] must not be blank")
