# 配置参考

[返回目录](README.md)

## Java 与基础设施

| 环境变量/配置 | 默认或要求 | 用途 |
| --- | --- | --- |
| server.port | 8123 | Java HTTP |
| RAG_DB_URL | jdbc:postgresql://localhost:5432/enterprise_rag；server 必填 | Java 数据库 URL |
| RAG_DB_USERNAME / RAG_DB_PASSWORD | 本地 rag/rag；server 必填 | Java 数据库凭据 |
| RAG_FLYWAY_BASELINE_ON_MIGRATE | false；server profile 硬编码 true | 非空库基线策略 |
| REDIS_HOST / PORT / PASSWORD | 127.0.0.1 / 6379 / 空 | Spring Redis 连接 |
| RAG_STORAGE_ENDPOINT | http://localhost:9000 | S3 endpoint |
| RAG_STORAGE_ACCESS_KEY_ID / SECRET_ACCESS_KEY | 无默认，必需 | S3 凭据 |
| RAG_STORAGE_BUCKET / REGION | rag-documents / us-east-1 | bucket、region |
| RAG_EMBEDDING_PYTHON_BASE_URL | http://localhost:9100 | Java → Python |
| RAG_EMBEDDING_MODEL / DIMENSION / BATCH_SIZE / TIMEOUT_SECONDS | text-embedding-v4 / 1536 / 10 / 60 | Java 入库 Embedding |
| JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH | 无默认，必需 | RSA PEM 路径 |
| RAG_CORS_ORIGINS | 两个本地 5173 Origin | 浏览器来源，逗号列表 |
| rag.security.jwt.issuer | enterprise-rag-agent | JWT issuer |
| rag.security.jwt.access-token-ttl / refresh-token-ttl | 15m / 7d | Token 生命周期 |
| rag.summary.* | Java 类默认 15/2000/5/500/10 | 摘要条件；当前 YAML 前缀错位 |
| rag.redis.enabled | false（代码 Value 默认） | Java 工作记忆开关；当前 YAML 前缀错位 |
| spring.servlet.multipart.* | 100MB / 120MB | 单文件/请求限制 |
| management.endpoints.web.exposure.include | health,info,metrics | Actuator 暴露 |

对象存储强制 pathStyle=true。Hikari 参数：maximumPoolSize=10、minimumIdle=2、connectionTimeout=10s、validationTimeout=3s、idleTimeout=300s、maxLifetime=600s、keepalive=120s。

Compose 使用 RAG_DB_NAME/USERNAME/PASSWORD/PORT，默认 enterprise_rag/rag/rag/5432。RAG_DB_NAME 只控制容器初始化库名，Java URL 和 Python POSTGRES_DB 仍需一致。

## Python 应用、模型和数据库

`app/config.py` 与 `rag/settings.py` 存在重复 Settings 定义；大多数运行组件使用 get_settings，Engine 可使用 RagSettings.from_env。修改变量时应检查具体 import。

| 环境变量 | 默认 | 用途 |
| --- | --- | --- |
| APP_NAME / APP_HOST / APP_PORT | enterprise-rag-python-api / 127.0.0.1 / 9100 | FastAPI 元数据和直接运行入口 |
| EMBEDDING_PROVIDER | mock | 标签；当前无真正 mock 分支 |
| EMBEDDING_BASE_URL / API_KEY | 空 | OpenAI 兼容 Embedding |
| EMBEDDING_MODEL / DIMENSION | mock-embedding-1536 / 1536 | 默认模型与维度 |
| EMBEDDING_BATCH_SIZE / TIMEOUT_SECONDS | 16 / 60 | 批量和超时 |
| LLM_PROVIDER | openai | Chat provider |
| LLM_BASE_URL / API_KEY | 回退 Embedding URL/key | Chat endpoint/凭据 |
| LLM_MODEL / TEMPERATURE / TIMEOUT_SECONDS | qwen-plus / 0.2 / 60 | Chat 参数 |
| LLM_FALLBACK1_* / LLM_FALLBACK2_* | gpt-3.5-turbo、URL/key 空 | 两级备用模型 |
| RERANK_ENABLED / PROVIDER | true / dashscope_qwen3 | 重排开关和适配器 |
| RERANK_BASE_URL / API_KEY / MODEL | 空 / 回退 LLM key / qwen3-rerank | 重排服务 |
| RERANK_CANDIDATE_TOP_K / FINAL_TOP_K | 20 / 8 | 精排候选和输出 |
| RERANK_MAX_DOCUMENT_CHARS / TIMEOUT_SECONDS | 6000 / 30 | 文档截断和超时 |
| POSTGRES_HOST / PORT / DB | 127.0.0.1 / 5432 / enterprise_rag | Python 数据库 |
| POSTGRES_USER / PASSWORD | 空 | 数据库凭据 |
| POSTGRES_POOL_MIN_SIZE / MAX_SIZE | 2 / 10 | psycopg 池 |
| POSTGRES_POOL_TIMEOUT_SECONDS / CONNECT_TIMEOUT_SECONDS | 10 / 10 | 池/连接超时 |
| JAVA_API_BASE_URL | http://localhost:8123 | Python 回调/协作预留 |

配置中包含 API key，日志和 Trace 不得输出。所有布尔值按字符串 lower()==true 解析。

## 检索、上下文与路由

| 环境变量 | 默认 | 用途 |
| --- | --- | --- |
| RAG_TOP_K / RAG_MAX_CONTEXT_CHARS | 5 / 6000 | 旧/通用 RAG topK、总上下文预算 |
| RAG_CONTEXT_MAX_DOCUMENT_CHARS | 5000 | 单文档预算 |
| RAG_CONTEXT_INCLUDE_SCORES | false | Prompt 是否含分数 |
| RAG_EMPTY_CONTEXT_MESSAGE | 代码内中文提示 | 无依据响应 |
| RETRIEVAL_VECTOR_TOP_K / KEYWORD_TOP_K | 30 / 30 | 两路召回 |
| RETRIEVAL_FUSION_TOP_K / FINAL_TOP_K | 20 / 15 | 融合及最终数量 |
| RETRIEVAL_RRF_K | 60 | RRF 常数 |
| RETRIEVAL_VECTOR_WEIGHT / KEYWORD_WEIGHT | 1.0 / 1.0 | 融合权重 |
| RETRIEVAL_ENABLE_KEYWORD | true | config.py 中关键词开关 |
| RETRIEVAL_MULTI_QUERY_ENABLED / TOP_K | true / 20 | 多查询 |
| RETRIEVAL_DEDUP_CONTENT_HASH | true | 内容哈希去重 |
| RETRIEVAL_SYNONYM_EXPANSION_ENABLED | true | 同义词扩展 |
| RETRIEVAL_SYNONYM_FILE | app/assets/synonyms.json | 同义词文件 |
| INTENT_WEIGHT_LLM / VECTOR | 0.7 / 0.3 | 意图融合 |
| INTENT_CONF_HIGH / LOW / GAP | 0.85 / 0.6 / 0.15 | 决策阈值 |
| INTENT_VECTOR_THRESHOLD_HIGH / LOW | 0.82 / 0.68 | 向量意图阈值 |
| INTENT_DEFAULT_ON_LOW_CONFIDENCE | CLARIFY | 低置信默认意图 |
| INTENT_EXAMPLES_FILE | app/assets/intent_examples.json | 意图样例 |
| INTENT_LLM_ENABLED | true | LLM 意图分支 |

资源文件相对路径受启动工作目录影响，应在实际进程中验证可解析。参数同时受调试请求覆盖时，以服务实现的 effective 值为准。

## 前端

| 变量/配置 | 默认 | 用途 |
| --- | --- | --- |
| VITE_API_BASE_URL | 空 | Axios/fetch 基址；空时开发代理 |
| Vite server.port | 5173 | 开发端口 |
| Vite proxy /api target | http://127.0.0.1:8123 | 本地 Java |
| Axios timeout | 30000ms | 普通 HTTP；SSE fetch 不用此超时 |

源码：[Java 配置](../../java-api/src/main/resources/application.yml)、[Python 配置](../../python-api/app/config.py)、[RAG 配置](../../python-api/app/rag/settings.py)、[Vite](../../frontend/vite.config.ts)。
