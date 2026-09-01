"""Embedding API.

这一层类似 Java 的 Controller：
- 接收 HTTP 请求。
- 把请求体转换成 Pydantic 对象。
- 调用 Service 层处理业务。
- 返回统一响应 ApiResult。
"""

from fastapi import APIRouter, Depends

from app.api.response import ApiResult
from app.schemas.embedding_schema import EmbeddingData, EmbeddingRequest
from app.rag.clients.embedding_service import EmbeddingService
from functools import lru_cache

# prefix="/api" 表示本文件下所有接口都会带 /api 前缀。
# tags=["embedding"] 用于 Swagger 文档分组。
router = APIRouter(prefix="/api", tags=["embedding"])



#@lru_cache
def get_embedding_service() -> EmbeddingService:
    """获取 EmbeddingService 单例。"""
    return EmbeddingService()


@router.post("/embeddings")
def create_embeddings(request: EmbeddingRequest,embedding_service: EmbeddingService = Depends(get_embedding_service)) -> ApiResult[EmbeddingData]:
    """Create embeddings for a list of texts.

    请求路径：POST /api/embeddings

    request 会由 FastAPI 自动从 JSON 请求体转换而来。
    返回值会由 FastAPI 自动转换为 JSON。
    """
    # Controller 不直接处理模型逻辑，而是委托给 Service。
    data = embedding_service.embed(request)
    return ApiResult.ok(data)
