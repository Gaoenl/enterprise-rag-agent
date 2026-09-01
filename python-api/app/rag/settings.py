"""RAG 核心库独立配置。

RagSettings 从环境变量直接读取（不依赖 app.config），保证 rag/ 核心库
可独立发布复用。字段名与现有 Settings 保持一致，便于逐步迁移。
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RagSettings:
    """RAG 核心运行配置。"""

    # ── LLM ──────────────────────────────────────
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float
    llm_timeout_seconds: int
    llm_fallback1_model: str
    llm_fallback1_base_url: str
    llm_fallback1_api_key: str
    llm_fallback2_model: str
    llm_fallback2_base_url: str
    llm_fallback2_api_key: str

    # ── Embedding ────────────────────────────────
    embedding_provider: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    embedding_dimension: int
    embedding_batch_size: int
    embedding_timeout_seconds: int

    # ── Rerank ───────────────────────────────────
    rerank_enabled: bool
    rerank_provider: str
    rerank_base_url: str
    rerank_api_key: str
    rerank_model: str
    rerank_candidate_top_k: int
    rerank_final_top_k: int
    rerank_max_document_chars: int
    rerank_timeout_seconds: int

    # ── 检索 ─────────────────────────────────────
    rag_top_k: int
    rag_max_context_chars: int
    retrieval_vector_top_k: int
    retrieval_keyword_top_k: int
    retrieval_final_top_k: int
    retrieval_rrf_k: int
    retrieval_vector_weight: float
    retrieval_keyword_weight: float
    retrieval_fusion_top_k: int
    retrieval_multi_query_enabled: bool
    retrieval_multi_query_top_k: int
    retrieval_dedup_content_hash: bool
    retrieval_synonym_expansion_enabled: bool
    retrieval_synonym_file: str
    rag_context_max_document_chars: int
    rag_empty_context_message: str
    rag_context_include_scores: bool

    # ── 意图 ─────────────────────────────────────
    intent_weight_llm: float
    intent_weight_vector: float
    intent_conf_high: float
    intent_conf_low: float
    intent_conf_gap: float
    intent_vector_threshold_high: float
    intent_vector_threshold_low: float
    intent_default_on_low_confidence: str
    intent_examples_file: str
    intent_llm_enabled: bool

    # ── 数据库 ───────────────────────────────────
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_pool_min_size: int
    postgres_pool_max_size: int
    postgres_pool_timeout_seconds: int
    postgres_connect_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "RagSettings":
        """从环境变量读取（默认值与 app/config.py 保持一致）。"""
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "openai"),
            llm_base_url=os.getenv(
                "LLM_BASE_URL",
                os.getenv("EMBEDDING_BASE_URL", ""),
            ),
            llm_api_key=os.getenv(
                "LLM_API_KEY",
                os.getenv("EMBEDDING_API_KEY", ""),
            ),
            llm_model=os.getenv("LLM_MODEL", "qwen-plus"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            llm_fallback1_model=os.getenv("LLM_FALLBACK1_MODEL", "gpt-3.5-turbo"),
            llm_fallback1_base_url=os.getenv("LLM_FALLBACK1_BASE_URL", ""),
            llm_fallback1_api_key=os.getenv("LLM_FALLBACK1_API_KEY", ""),
            llm_fallback2_model=os.getenv("LLM_FALLBACK2_MODEL", "gpt-3.5-turbo"),
            llm_fallback2_base_url=os.getenv("LLM_FALLBACK2_BASE_URL", ""),
            llm_fallback2_api_key=os.getenv("LLM_FALLBACK2_API_KEY", ""),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "mock"),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL", ""),
            embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
            embedding_model=os.getenv("EMBEDDING_MODEL", "mock-embedding-1536"),
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", "1536")),
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
            embedding_timeout_seconds=int(
                os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")
            ),
            rerank_enabled=os.getenv("RERANK_ENABLED", "true").lower() == "true",
            rerank_provider=os.getenv("RERANK_PROVIDER", "dashscope_qwen3"),
            rerank_base_url=os.getenv("RERANK_BASE_URL", ""),
            rerank_api_key=os.getenv("RERANK_API_KEY", os.getenv("LLM_API_KEY", "")),
            rerank_model=os.getenv("RERANK_MODEL", "qwen3-rerank"),
            rerank_candidate_top_k=int(os.getenv("RERANK_CANDIDATE_TOP_K", "20")),
            rerank_final_top_k=int(os.getenv("RERANK_FINAL_TOP_K", "8")),
            rerank_max_document_chars=int(
                os.getenv("RERANK_MAX_DOCUMENT_CHARS", "6000")
            ),
            rerank_timeout_seconds=int(os.getenv("RERANK_TIMEOUT_SECONDS", "30")),
            rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
            rag_max_context_chars=int(os.getenv("RAG_MAX_CONTEXT_CHARS", "6000")),
            retrieval_vector_top_k=int(os.getenv("RETRIEVAL_VECTOR_TOP_K", "30")),
            retrieval_keyword_top_k=int(
                os.getenv("RETRIEVAL_KEYWORD_TOP_K", "30")
            ),
            retrieval_final_top_k=int(os.getenv("RETRIEVAL_FINAL_TOP_K", "15")),
            retrieval_rrf_k=int(os.getenv("RETRIEVAL_RRF_K", "60")),
            retrieval_vector_weight=float(
                os.getenv("RETRIEVAL_VECTOR_WEIGHT", "1.0")
            ),
            retrieval_keyword_weight=float(
                os.getenv("RETRIEVAL_KEYWORD_WEIGHT", "1.0")
            ),
            retrieval_fusion_top_k=int(os.getenv("RETRIEVAL_FUSION_TOP_K", "20")),
            retrieval_multi_query_enabled=(
                os.getenv("RETRIEVAL_MULTI_QUERY_ENABLED", "true").lower() == "true"
            ),
            retrieval_multi_query_top_k=int(
                os.getenv("RETRIEVAL_MULTI_QUERY_TOP_K", "20")
            ),
            retrieval_dedup_content_hash=(
                os.getenv("RETRIEVAL_DEDUP_CONTENT_HASH", "true").lower() == "true"
            ),
            retrieval_synonym_expansion_enabled=(
                os.getenv("RETRIEVAL_SYNONYM_EXPANSION_ENABLED", "true").lower()
                == "true"
            ),
            retrieval_synonym_file=os.getenv(
                "RETRIEVAL_SYNONYM_FILE", "assets/synonyms.json"
            ),
            rag_context_max_document_chars=int(
                os.getenv("RAG_CONTEXT_MAX_DOCUMENT_CHARS", "5000")
            ),
            rag_empty_context_message=os.getenv(
                "RAG_EMPTY_CONTEXT_MESSAGE",
                "根据当前知识库中的资料，暂时没有找到能够回答该问题的充分依据。",
            ),
            rag_context_include_scores=(
                os.getenv("RAG_CONTEXT_INCLUDE_SCORES", "false").lower() == "true"
            ),
            intent_weight_llm=float(os.getenv("INTENT_WEIGHT_LLM", "0.7")),
            intent_weight_vector=float(os.getenv("INTENT_WEIGHT_VECTOR", "0.3")),
            intent_conf_high=float(os.getenv("INTENT_CONF_HIGH", "0.85")),
            intent_conf_low=float(os.getenv("INTENT_CONF_LOW", "0.6")),
            intent_conf_gap=float(os.getenv("INTENT_CONF_GAP", "0.15")),
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
                "INTENT_EXAMPLES_FILE", "assets/intent_examples.json"
            ),
            intent_llm_enabled=(
                os.getenv("INTENT_LLM_ENABLED", "true").lower() == "true"
            ),
            postgres_host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("POSTGRES_DB", "enterprise_rag"),
            postgres_user=os.getenv("POSTGRES_USER", ""),
            postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
            postgres_pool_min_size=int(os.getenv("POSTGRES_POOL_MIN_SIZE", "2")),
            postgres_pool_max_size=int(os.getenv("POSTGRES_POOL_MAX_SIZE", "10")),
            postgres_pool_timeout_seconds=int(
                os.getenv("POSTGRES_POOL_TIMEOUT_SECONDS", "10")
            ),
            postgres_connect_timeout_seconds=int(
                os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "10")
            ),
        )
