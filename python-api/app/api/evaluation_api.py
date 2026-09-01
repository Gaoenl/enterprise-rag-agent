"""RAG 检索测评 API。"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.response import ApiResult
from app.schemas.evaluation_schema import (
    EvaluationCreateRequest,
    EvaluationResultData,
    EvaluationRunData,
)
from app.apps.evaluation.evaluation_service import EvaluationService


router = APIRouter(prefix="/api/evaluations/retrieval", tags=["rag-evaluation"])


@lru_cache
def get_evaluation_service() -> EvaluationService:
    """创建进程级评测任务管理器。"""
    return EvaluationService()


@router.post("", response_model=ApiResult[EvaluationRunData], response_model_by_alias=True)
def create_evaluation(
    request: EvaluationCreateRequest,
    service: EvaluationService = Depends(get_evaluation_service),
) -> ApiResult[EvaluationRunData]:
    """创建异步检索评测任务。"""
    return ApiResult.ok(service.create(request))


@router.get("/{run_id}", response_model=ApiResult[EvaluationRunData], response_model_by_alias=True)
def get_evaluation(
    run_id: str,
    tenant_id: int = Query(..., alias="tenantId"),
    user_id: int = Query(..., alias="userId"),
    service: EvaluationService = Depends(get_evaluation_service),
) -> ApiResult[EvaluationRunData]:
    """查询评测进度。"""
    try:
        return ApiResult.ok(service.get_status(run_id, tenant_id, user_id))
    except KeyError as exception:
        raise HTTPException(status_code=404, detail=str(exception)) from exception
    except PermissionError as exception:
        raise HTTPException(status_code=403, detail=str(exception)) from exception


@router.get(
    "/{run_id}/result",
    response_model=ApiResult[EvaluationResultData],
    response_model_by_alias=True,
)
def get_evaluation_result(
    run_id: str,
    tenant_id: int = Query(..., alias="tenantId"),
    user_id: int = Query(..., alias="userId"),
    service: EvaluationService = Depends(get_evaluation_service),
) -> ApiResult[EvaluationResultData]:
    """查询评测结果。"""
    try:
        return ApiResult.ok(service.get_result(run_id, tenant_id, user_id))
    except KeyError as exception:
        raise HTTPException(status_code=404, detail=str(exception)) from exception
    except PermissionError as exception:
        raise HTTPException(status_code=403, detail=str(exception)) from exception
