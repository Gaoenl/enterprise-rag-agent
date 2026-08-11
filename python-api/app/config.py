"""Application configuration.

这个文件负责读取 Python 服务运行配置。

如果类比 Java：
- Settings 类似 @ConfigurationProperties 对应的配置类。
- os.getenv(...) 类似从 application.yml 或环境变量读取配置。
- get_settings() 类似提供一个全局可复用的配置 Bean。
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from dotenv import load_dotenv
load_dotenv()
@dataclass(frozen=True)
class Settings:
    """Runtime settings for python-api.

    dataclass 可以理解为 Python 版的简单 DTO。
    frozen=True 表示创建后不允许修改，避免运行时配置被误改。
    """

    # Python API 服务自身配置。
    app_name: str
    app_host: str
    app_port: int

    # Embedding 模型相关配置。
    # 当前 provider 默认为 mock，后续可以扩展为 openai-compatible、dashscope 等。
    embedding_provider: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    embedding_dimension: int
    embedding_batch_size: int
    embedding_timeout_seconds: int

    # LLM chat model settings.
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float
    llm_timeout_seconds: int
    # LLM 备用模型 1
    llm_fallback1_model: str
    llm_fallback1_base_url: str
    llm_fallback1_api_key: str
    # LLM 备用模型 2
    llm_fallback2_model: str
    llm_fallback2_base_url: str
    llm_fallback2_api_key: str

    # PostgreSQL
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    # RAG
    rag_top_k: int
    rag_max_context_chars: int
    # 混合检索配置。
    retrieval_vector_top_k: int
    retrieval_keyword_top_k: int
    retrieval_final_top_k: int
    retrieval_rrf_k: int
    retrieval_vector_weight: float
    retrieval_keyword_weight: float
    retrieval_enable_keyword: bool

    # Rerank 精排配置。
    retrieval_fusion_top_k: int
    rerank_enabled: bool
    rerank_provider: str
    rerank_base_url: str
    rerank_api_key: str
    rerank_model: str
    rerank_candidate_top_k: int
    rerank_final_top_k: int
    rerank_max_document_chars: int
    rerank_timeout_seconds: int
    # 单个分片进入上下文时允许的最大字符数。
    rag_context_max_document_chars: int

    # RAG 没有检索结果时返回的提示。
    rag_empty_context_message: str

    # 是否将检索分数写进 LLM 上下文。
    rag_context_include_scores: bool

    # PostgreSQL 连接池配置。
    postgres_pool_min_size: int
    postgres_pool_max_size: int
    postgres_pool_timeout_seconds: int
    postgres_connect_timeout_seconds: int
    java_api_base_url: str
    # 意图路由配置。
    intent_vector_threshold_high: float
    intent_vector_threshold_low: float
    intent_default_on_low_confidence: str
    intent_examples_file: str

    intent_llm_enabled: bool





@lru_cache
def get_settings() -> Settings:
    """Read settings once and cache them for the current process.

    @lru_cache 的作用是缓存函数返回值。
    这样整个进程里多次调用 get_settings() 时，只会创建一个 Settings 对象。
    """
    return Settings(
        # 第一个参数是环境变量名，第二个参数是默认值。
        # 例如没有设置 APP_NAME 时，就使用 enterprise-rag-python-api。
        app_name=os.getenv("APP_NAME", "enterprise-rag-python-api"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "9100")),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "mock"),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL", ""),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
        embedding_model=os.getenv("EMBEDDING_MODEL", "mock-embedding-1536"),
        embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", "1536")),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
        embedding_timeout_seconds=int(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_base_url=os.getenv("LLM_BASE_URL", os.getenv("EMBEDDING_BASE_URL", "")),
        llm_api_key=os.getenv("LLM_API_KEY", os.getenv("EMBEDDING_API_KEY", "")),
        llm_model=os.getenv("LLM_MODEL", "qwen-plus"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        llm_fallback1_model=os.getenv("LLM_FALLBACK1_MODEL", "gpt-3.5-turbo"),
        llm_fallback1_base_url=os.getenv("LLM_FALLBACK1_BASE_URL", ""),
        llm_fallback1_api_key=os.getenv("LLM_FALLBACK1_API_KEY", ""),
        llm_fallback2_model=os.getenv("LLM_FALLBACK2_MODEL", "gpt-3.5-turbo"),
        llm_fallback2_base_url=os.getenv("LLM_FALLBACK2_BASE_URL", ""),
        llm_fallback2_api_key=os.getenv("LLM_FALLBACK2_API_KEY", ""),
        postgres_host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=os.getenv("POSTGRES_DB", "enterprise_rag"),
        postgres_user=os.getenv("POSTGRES_USER", ""),
        postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
        rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
        rag_max_context_chars=int(os.getenv("RAG_MAX_CONTEXT_CHARS", "6000")),
        retrieval_vector_top_k=int(
            os.getenv("RETRIEVAL_VECTOR_TOP_K", "30")
        ),
        retrieval_keyword_top_k=int(
            os.getenv("RETRIEVAL_KEYWORD_TOP_K", "30")
        ),
        retrieval_final_top_k=int(
            os.getenv("RETRIEVAL_FINAL_TOP_K", "15")
        ),
        retrieval_rrf_k=int(
            os.getenv("RETRIEVAL_RRF_K", "60")
        ),
        retrieval_vector_weight=float(
            os.getenv("RETRIEVAL_VECTOR_WEIGHT", "1.0")
        ),
        retrieval_keyword_weight=float(
            os.getenv("RETRIEVAL_KEYWORD_WEIGHT", "1.0")
        ),
        retrieval_enable_keyword=(
                os.getenv("RETRIEVAL_ENABLE_KEYWORD", "true").lower()
                == "true"
        ),
        retrieval_fusion_top_k=int(
            os.getenv("RETRIEVAL_FUSION_TOP_K", "20")
        ),

        rerank_enabled=(
                os.getenv("RERANK_ENABLED", "true").lower() == "true"
        ),
        rerank_provider=os.getenv(
            "RERANK_PROVIDER",
            "dashscope_qwen3",
        ),
        rerank_base_url=os.getenv(
            "RERANK_BASE_URL",
            "",
        ),
        rerank_api_key=os.getenv(
            "RERANK_API_KEY",
            os.getenv("LLM_API_KEY", ""),
        ),
        rerank_model=os.getenv(
            "RERANK_MODEL",
            "qwen3-rerank",
        ),
        rerank_candidate_top_k=int(
            os.getenv("RERANK_CANDIDATE_TOP_K", "20")
        ),
        rerank_final_top_k=int(
            os.getenv("RERANK_FINAL_TOP_K", "8")
        ),
        rerank_max_document_chars=int(
            os.getenv("RERANK_MAX_DOCUMENT_CHARS", "6000")
        ),
        rerank_timeout_seconds=int(
            os.getenv("RERANK_TIMEOUT_SECONDS", "30")
        ),
        rag_context_max_document_chars=int(
            os.getenv(
                "RAG_CONTEXT_MAX_DOCUMENT_CHARS",
                "5000",
            )
        ),
        rag_empty_context_message=os.getenv(
            "RAG_EMPTY_CONTEXT_MESSAGE",
            "根据当前知识库中的资料，"
            "暂时没有找到能够回答该问题的充分依据。",
        ),
        rag_context_include_scores=(
                os.getenv(
                    "RAG_CONTEXT_INCLUDE_SCORES",
                    "false",
                ).lower()
                == "true"
        ),
        postgres_pool_min_size=int(
            os.getenv("POSTGRES_POOL_MIN_SIZE", "2")
        ),
        postgres_pool_max_size=int(
            os.getenv("POSTGRES_POOL_MAX_SIZE", "10")
        ),
        postgres_pool_timeout_seconds=int(
            os.getenv("POSTGRES_POOL_TIMEOUT_SECONDS", "10")
        ),
        postgres_connect_timeout_seconds=int(
            os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "10")
        ),
        java_api_base_url=os.getenv("JAVA_API_BASE_URL", "http://localhost:8123"),
        intent_vector_threshold_high=float(
            os.getenv("INTENT_VECTOR_THRESHOLD_HIGH", "0.82")
        ),
        intent_vector_threshold_low=float(
            os.getenv("INTENT_VECTOR_THRESHOLD_LOW", "0.68")
        ),
        intent_default_on_low_confidence=os.getenv(
            "INTENT_DEFAULT_ON_LOW_CONFIDENCE", "knowledge"
        ),
        intent_examples_file=os.getenv(
            "INTENT_EXAMPLES_FILE", "config/intent_examples.json"
        ),
        intent_llm_enabled=(
                os.getenv("INTENT_LLM_ENABLED", "true").lower() == "true"
        )
    )
