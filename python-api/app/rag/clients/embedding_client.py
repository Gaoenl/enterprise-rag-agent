"""Embedding model client.

Client 层负责和外部模型服务交互。

支持按模型名称缓存多个客户端实例，实现入库流水线按任务切换 Embedding 模型。
"""
from app.rag.errors import EmbeddingError
from langchain_openai import OpenAIEmbeddings

from app.config import get_settings


class EmbeddingClient:
    """langchain embedding 客户端，按 model 参数动态创建/缓存客户端实例。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        # 模型 → 客户端缓存，避免为同一模型重复创建实例。
        self._clients: dict[tuple[str, int | None], OpenAIEmbeddings] = {}
        # 预热默认模型客户端。
        self._get_or_create_client(
            self._settings.embedding_model,
            self._settings.embedding_dimension,
        )

    def _get_or_create_client(
            self,
            model: str,
            dimension: int | None = None,
    ) -> OpenAIEmbeddings:
        key = (model, dimension)
        if key not in self._clients:
            kwargs = dict(
                model=model,
                api_key=self._settings.embedding_api_key,
                base_url=self._settings.embedding_base_url,
                request_timeout=self._settings.embedding_timeout_seconds,
                check_embedding_ctx_length=False,
            )
            # 有维度则显式指定；不传时由模型返回默认维度。
            if dimension is not None:
                kwargs["dimensions"] = dimension
            self._clients[key] = OpenAIEmbeddings(**kwargs)
        return self._clients[key]

    def embed_texts(
            self,
            texts: list[str],
            model: str | None = None,
            dimension: int | None = None,
    ) -> list[list[float]]:
        """批量生成文本向量。

        Args:
            texts: 待向量化的文本列表。
            model: 指定模型名称，None 则使用全局默认模型。
            dimension: 指定向量维度，None 则使用全局默认维度。
        """
        effective_model = model or self._settings.embedding_model
        effective_dimension = (
            dimension
            if dimension is not None
            else self._settings.embedding_dimension
        )
        client = self._get_or_create_client(
            effective_model, effective_dimension
        )

        try:
            vectors = client.embed_documents(texts)
        except Exception as exc:
            raise EmbeddingError(f"Call LangChain embedding model failed: {exc}",
            ) from exc

        self._validate_vectors(vectors, len(texts),effective_dimension)
        return vectors

    def embed_query(
            self,
            text: str,
            model: str | None = None,
            dimension: int | None = None,
    ) -> list[float]:
        """生成用户问题向量，后续 RAG 检索会复用。"""
        effective_model = model or self._settings.embedding_model
        effective_dimension = (
            dimension
            if dimension is not None
            else self._settings.embedding_dimension
        )
        client = self._get_or_create_client(
            effective_model, effective_dimension
        )
        try:
            vector = client.embed_query(text)
        except Exception as exc:
            raise EmbeddingError(f"Call LangChain query embedding failed: {exc}",
            ) from exc

        self._validate_vector(vector,effective_dimension)
        return vector

    def _validate_vectors(
        self,
        vectors: list[list[float]],
        expected_size: int,
        expected_dimension: int | None,
    ) -> None:
        if len(vectors) != expected_size:
            raise EmbeddingError((
                    "Embedding count mismatch: "
                    f"expected={expected_size}, actual={len(vectors)}"
                ),
            )
        for vector in vectors:
            self._validate_vector(vector, expected_dimension)



    def _validate_vector(
        self,
        vector: list[float],
        expected_dimension: int | None,
    ) -> None:
        if (
            expected_dimension is not None
            and len(vector) != expected_dimension
        ):
            raise EmbeddingError((
                    "Embedding dimension mismatch: "
                    f"expected={expected_dimension}, actual={len(vector)}"
                ),
            )
