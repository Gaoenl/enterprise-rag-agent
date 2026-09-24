"""FastAPI application entry point.

这个文件是 Python API 服务的启动入口。

如果类比 Java：
- app.main 类似 Spring Boot 的启动类 RagApiApplication。
- FastAPI() 类似创建一个 Web 应用容器。
- include_router(...) 类似注册 Controller。
"""

import uvicorn
from fastapi import FastAPI

from app.api.chat_api import (
    close_chat_service,
    router as chat_router,
)
from app.api.embedding_api import router as embedding_router
from app.api.health_api import router as health_router
from app.config import get_settings
from app.api.retrieval_debug_api import (
    router as retrieval_debug_router,
)
from app.api.conversation_summary_api import router as summary_router
from app.api.evaluation_api import router as evaluation_router
from app.api.errors import register_error_handlers
from contextlib import asynccontextmanager

from app.rag.db.postgres import (
    close_connection_pool,
    init_connection_pool,
)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理数据库连接池的启动和关闭。"""
    # 应用启动时创建并预热连接。
    init_connection_pool()

    try:
        yield
    finally:
        close_chat_service()
        # 应用停止时释放物理数据库连接。
        close_connection_pool()
def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    单独抽出 create_app 方法，是为了后续测试和扩展更方便。
    测试代码可以直接 import app，也可以调用 create_app 创建新实例。
    """
    # 读取运行配置，例如应用名称、端口、Embedding 默认维度等。
    settings = get_settings()

    # 创建 FastAPI 应用对象。
    # 这里的 title/version/description 会显示在 Swagger 页面中。
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Python model and RAG orchestration API for the enterprise RAG project.",
        lifespan=lifespan,
    )

    # 注册 RAG 核心异常处理器。
    register_error_handlers(app)

    # 注册 API 路由。
    # 每个 router 可以理解为一组 Controller 方法。
    app.include_router(health_router)
    app.include_router(embedding_router)
    app.include_router(chat_router)
    # 注册检索调试接口。
    app.include_router(retrieval_debug_router)
    # 注册异步 RAG 检索测评接口。
    app.include_router(evaluation_router)

    app.include_router(summary_router)

    return app


# uvicorn 启动时会加载这个 app 变量。
# 例如命令：uvicorn app.main:app --port 9100
app = create_app()


if __name__ == "__main__":
    # 直接运行 python app/main.py 时，会进入这里。
    # 实际开发中更常用 uvicorn app.main:app --reload 启动。
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
