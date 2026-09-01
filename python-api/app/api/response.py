"""Unified API response model.

这个文件定义 Python API 的统一响应结构。
它刻意和 Java 的 ApiResult 风格保持一致，方便 Java 后续调用 Python。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

# TypeVar 用于声明泛型类型。
# ApiResult[EmbeddingData] 表示 data 字段是 EmbeddingData。
T = TypeVar("T")


class ApiResult(BaseModel, Generic[T]):
    """Response format shared by Python APIs.

    It intentionally looks similar to the Java ApiResult so Java can parse
    Python responses with less special handling.
    """

    success: bool
    code: str
    message: str
    data: T | None = None

    @staticmethod
    def ok(data: T | None = None) -> "ApiResult[T]":
        """Create a successful response."""
        return ApiResult(success=True, code="OK", message="success", data=data)

    @staticmethod
    def fail(code: str, message: str) -> "ApiResult[None]":
        """Create a failed response."""
        return ApiResult(success=False, code=code, message=message, data=None)
