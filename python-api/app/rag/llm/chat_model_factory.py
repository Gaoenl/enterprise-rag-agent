"""统一创建 LangChain ChatModel。"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from app.config import get_settings


@lru_cache
def get_chat_model() -> ChatOpenAI:
    """创建并缓存全局聊天模型实例。"""
    settings = get_settings()

    # DeepSeek 使用专用 ChatDeepSeek 客户端（init_chat_model 不支持 deepseek provider）。
    if settings.llm_provider == "deepseek":
        return ChatDeepSeek(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            request_timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    return init_chat_model(
        model=settings.llm_model,
        model_provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        extra_body={
            "thinking": {
                "type": "disabled",
            }
        },
)
