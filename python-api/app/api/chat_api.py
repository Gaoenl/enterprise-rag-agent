""""Chat API。提供两种聊天接口：

    1. POST /api/chat/completions
   普通 JSON 响应，等待完整回答生成后一次性返回。

    2. POST /api/chat/stream
   SSE 流式响应，模型生成一部分就返回一部分。
"""


from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.api.response import ApiResult
from app.schemas.chat_schema import ChatData, ChatRequest
from app.apps.chat.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@lru_cache
def get_chat_service() -> ChatService:
    """Return a cached ChatService instance."""
    return ChatService()


@router.post("/completions")
def create_chat_completion(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ApiResult[ChatData]:
    """Create a basic answer for a user question."""
    data = chat_service.answer(request)
    return ApiResult.ok(data)
@router.post(
    "/stream",
    response_class=StreamingResponse,
responses={
        200: {
            "description": "SSE streaming chat response.",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "string",
                    }
                }
            },
        }
    },
)
def create_stream_chat_completion(
request: ChatRequest,
    chat_service: ChatService = Depends(
        get_chat_service
    ),
)->StreamingResponse:
    """执行 SSE 流式聊天。

        响应由多个 SSE 事件组成：

        start -> route -> retrieval -> delta... ->
        final -> done

        出现异常时：

        start -> ... -> error -> done
        """
    event_iterator = chat_service.stream_answer(
        request
    )
    # StreamingResponse 每次从生成器取得一个字符串，
    # 就立即将该字符串写入 HTTP 响应。
    return StreamingResponse(
        content=event_iterator,
        media_type="text/event-stream",
        headers={
            # 禁止浏览器或代理缓存事件流。
            "Cache-Control": "no-cache",

            # 提示 Nginx 不要缓冲 SSE 响应。
            "X-Accel-Buffering": "no",

            # 当前响应需要保持长连接。
            "Connection": "keep-alive",
        },
    )
