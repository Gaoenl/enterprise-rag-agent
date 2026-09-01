"""Health check API.

健康检查接口用于确认 Python 服务是否正常启动。
Java 服务、Docker、负载均衡或运维脚本都可以调用这个接口探活。
"""

from fastapi import APIRouter

from app.api.response import ApiResult

# APIRouter 类似一组 Controller。
# tags 会显示在 FastAPI Swagger 文档中，方便接口分组。
router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> ApiResult[dict]:
    """Return service health status.

    返回格式使用 ApiResult，是为了和 Java 的响应结构保持一致。
    """
    return ApiResult.ok({"status": "UP"})
