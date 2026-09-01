"""API 层异常处理：把 RAG 核心库异常转换为 HTTP 响应。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.rag.errors import (
    ConfigurationError,
    EmbeddingError,
    IntentError,
    InvalidQueryError,
    LLMError,
    RagError,
    RetrievalError,
)


_STATUS_MAP = {
    InvalidQueryError: 400,
    ConfigurationError: 500,
    EmbeddingError: 502,
    LLMError: 502,
    RetrievalError: 502,
    IntentError: 502,
}


def register_error_handlers(app: FastAPI) -> None:
    """注册 RAG 核心异常处理器。"""

    @app.exception_handler(RagError)
    async def _rag_error_handler(
        request: Request,
        exc: RagError,
    ) -> JSONResponse:
        status_code = _STATUS_MAP.get(type(exc), 500)
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "code": type(exc).__name__,
                "message": str(exc),
            },
        )
