from functools import lru_cache

from fastapi import APIRouter, Depends

from app.api.response import ApiResult
from app.schemas.conversation_summary_schema import (
    SummarizeRequest,
    SummarizeResponse,
)
from app.apps.chat.summary_service import (
    ConversationSummaryService,
)

router = APIRouter(prefix="/api/conversations", tags=["conversation-summary"])


@lru_cache
def get_summary_service() -> ConversationSummaryService:
    return ConversationSummaryService()


@router.post(
    "/summarize",
    response_model=ApiResult[SummarizeResponse],
    response_model_by_alias=True,
)
def summarize(
    request: SummarizeRequest,
    service: ConversationSummaryService = Depends(get_summary_service),
) -> ApiResult[SummarizeResponse]:
    return ApiResult.ok(
        SummarizeResponse(summary=service.summarize(request))
    )