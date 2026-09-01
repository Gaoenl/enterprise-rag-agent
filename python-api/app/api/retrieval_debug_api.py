"""检索调试 API。"""

from functools import lru_cache

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.api.response import ApiResult
from app.schemas.retrieval_debug_schema import (
    RetrievalConfigData,
    RetrievalDebugData,
    RetrievalDebugRequest,
)
from app.apps.evaluation.debug_service import (
    RetrievalDebugService,
)


router = APIRouter(
    prefix="/api/retrieval",
    tags=["retrieval-debug"],
)


@lru_cache
def get_retrieval_debug_service() -> RetrievalDebugService:
    """创建并缓存检索调试 Service。

    类似 Spring 中默认的单例 Service Bean。
    检索器、模型客户端和数据库配置不需要每次请求重新创建。
    """
    return RetrievalDebugService()


@router.post(
    "/debug",
    response_model=ApiResult[RetrievalDebugData],
    response_model_by_alias=True,
)
def debug_retrieval(
    request: RetrievalDebugRequest,
    service: RetrievalDebugService = Depends(
        get_retrieval_debug_service
    ),
) -> ApiResult[RetrievalDebugData]:
    """执行检索调试，但不生成最终回答。

    执行过程：

    Query Rewrite
        -> Vector / Keyword Search
        -> RRF
        -> Rerank
        -> Context Packing
    """
    data = service.debug(request)

    return ApiResult.ok(data)


@router.get(
    "/config",
    response_model=ApiResult[RetrievalConfigData],
    response_model_by_alias=True,
)
def get_retrieval_config() -> ApiResult[RetrievalConfigData]:
    """返回检索调试默认参数，供前端按服务端配置初始化表单。"""
    settings = get_settings()
    return ApiResult.ok(
        RetrievalConfigData(
            vector_top_k=settings.retrieval_vector_top_k,
            keyword_top_k=settings.retrieval_keyword_top_k,
            fusion_top_k=settings.retrieval_fusion_top_k,
            final_top_k=settings.retrieval_final_top_k,
            rrf_k=settings.retrieval_rrf_k,
            vector_weight=settings.retrieval_vector_weight,
            keyword_weight=settings.retrieval_keyword_weight,
            multi_query_enabled=(
                settings.retrieval_multi_query_enabled
            ),
            multi_query_top_k=(
                settings.retrieval_multi_query_top_k
            ),
            synonym_expansion_enabled=(
                settings.retrieval_synonym_expansion_enabled
            ),
        )
    )
