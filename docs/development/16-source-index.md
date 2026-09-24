# 源码与历史文档索引

[返回目录](README.md)

此索引覆盖业务代码、配置、迁移、测试、脚本、数据集和已有文档类别。大量生成的 CRUD-RAG 文档按数据集目录收录，不逐一列出近千个文本文件。

## 根目录

| 路径 | 内容 |
| --- | --- |
| `pom.xml` | Maven 聚合、Java/Spring 版本 |
| `docker-compose.yml` | PostgreSQL/pgvector |
| `.env.example`, `.env.server.example` | 示例配置；需与实际读取点核对 |
| `README.md` | 项目概览，部分描述已过时 |
| `AGENTS.md`, `docs/agents/*` | Agent 工作、Issue、领域文档约定 |
| `data`, `output`, `tmp` | 运行/实验资产目录，内容不是业务模块 |
| `secrets` | 本地密钥目录，不应提交或写入文档 |

## Java 源码

根包 `java-api/src/main/java/com/example/rag`：

| 目录 | 核心文件/子目录 |
| --- | --- |
| auth | controller/AuthController；config/SecurityConfig、Jwt*、PasswordConfig；security/JwtTokenService、TokenVersionValidator、RefreshTokenGenerator、401/403 handler；service/impl；dto/entity/mapper |
| tenant | TenantController、TenantService/Impl、SysTenantMapper、SysTenant、TenantCreateRequest |
| user | UserController、UserService/Impl、SysUserMapper、SysUser、UserCreateRequest/UserResponse |
| knowledge | KnowledgeBase/Document Controller、Service/Impl、Mapper、Entity、DTO、DocumentProcessStatus |
| ingestion | controller；event；pipeline 的 StepCode/PipelineStep/Parse/Embed/Complete/IngestionPipeline/线程池；processor；parser；chunk；task 服务、重试、查询、指标；entity/dto/mapper/enums/config |
| embedding | PythonEmbeddingClient、EmbeddingClient、ChunkEmbeddingService/Impl、EmbeddingBatchPersistenceService、Properties 和 DTO |
| chat | ChatController；ChatService/Impl；ChatPersistenceService；Python Chat/Summary 客户端和 SSE 解析；会话/消息 Entity/Mapper/DTO；缓存、流/摘要执行器与 Properties；ConversationSummaryService |
| evaluation | RetrievalDebug/Evaluation Controller、Service/Impl、Python clients 及 DTO |
| model | ModelProvider/Config 管理 Controller、查询 Controller、Service/Impl、Mapper、Entity 与 DTO |
| trace | Controller、Service/Impl、Mapper、Entity、DTO、RagTraceContext/Root/Node |
| common/api | ApiResult、PageQuery、PageResult |
| common/error | 错误码与各类异常 |
| common/context/web/security | 当前用户/请求上下文、过滤器、全局异常、SSE、TenantAccessGuard |
| common/config | 数据库 TypeHandler/填充/配置及 S3 配置 |
| common/storage/id/utils/enums | S3、Snowflake、文件哈希、角色和状态 |

资源：`application.yml`、`application-server.yml`、`mapper/ingestion/IngestionTaskMapper.xml`、`db/migration/V1..V19`。Java 当前无 `src/test`。

## Python 源码

根目录 `python-api/app`：

| 目录/文件 | 内容 |
| --- | --- |
| main.py, config.py | FastAPI 生命周期/路由、主配置 |
| api | health、embedding、chat、summary、retrieval debug、evaluation、ApiResult、错误映射 |
| apps/chat | ChatService、ConversationSummaryService |
| apps/evaluation | DebugService、EvaluationService、模型与 CRUD 数据准备器 |
| rag/engine.py, settings.py, errors.py | 核心入口、独立配置、异常 |
| rag/clients | Embedding service/client、LLM、Rerank 客户端 |
| rag/router | 规则、向量、LLM、融合、知识库选择 |
| rag/rewriter | 对话问题独立化、检索改写 |
| rag/retriever | pgvector、keyword、parallel、hybrid、RRF、rerank、关键词与工具函数 |
| rag/context, postprocess | 上下文打包、引用后处理 |
| rag/db, trace, tools, llm | psycopg 池、Trace、calculator、模型工厂 |
| rag/schemas | routing/retrieval/rerank/context |
| rag/workflow | 当前只有预留 init |
| schemas | answer/chat/execution/embedding/evaluation/retrieval debug/stream/summary/trace |
| streaming | SSE encoder |
| memory | 迁移中的 database/models/store/postgres_store |
| assets | intent_examples.json、synonyms.json |

依赖与启动：`requirements.txt`、`Dockerfile`、`README.md`、`PYTHON_DEVELOPMENT_FLOW.md`。

Python 测试：`test_embedding_api.py`、`test_chat_stream_api.py`、`test_sse_encoder.py`、`test_trace_recorder.py`、`test_rrf_fusion.py`、`test_intent_router.py`、`test_answer_postprocessor.py`。

脚本：`scripts/prepare_crud_v1.py`、`prepare_crud_v2.py`、`generate_test_kb.py`、`evaluate_intent.py`。测评数据位于 `app/apps/evaluation/datasets/intent_v1.json`、`crud_v1`、`crud_v2`；每个 CRUD 数据集含 manifest、cases、summary 和 documents。

## 前端源码

| 目录/文件 | 内容 |
| --- | --- |
| main.tsx, router/AppRouter.tsx | 入口和全部注册路由 |
| router/AdminRouteGuard.tsx | 管理角色守卫 |
| layouts | ConsoleLayout、AdminLayout |
| pages | Login、Chat、Dashboard、Knowledge、Documents、Task、RagEvaluation、Trace、Model、admin/Settings；另有未注册 Home/Placeholder/RetrievalDebug |
| api/http.ts | Axios、JSONBig、Refresh、错误 |
| api/modules.ts | 主要业务 API 与 Chat SSE |
| api/retrieval.ts, evaluation.ts | 检索/测评调用 |
| components | Markdown、ErrorBoundary、PageHeader、ProcessingStatusChart、检索表格与上下文查看 |
| stores/authStore.ts | 登录 Token 与用户 |
| types | api、retrieval、evaluation |
| styles/global.css, utils/role.ts | 全局样式和角色 |
| package.json, vite.config.ts, eslint.config.js, tsconfig* | 构建与质量配置 |

## 现有 docs 分类

| 文档 | 定位 |
| --- | --- |
| system-overview-and-roadmap.md | 早期总览与规划，更新时间较早 |
| architecture-flowcharts.md | 核心流程图，需与当前代码核对 |
| frontend-backend-integration-analysis.md | 对接分析；首行存在 `z#` 排版问题 |
| sql-v1-init-pg-schema-explained.md | V1 解释，不含全部增量 |
| step-01 至 step-13、step-25、step-29/30 | 分阶段开发记录，适合追溯设计背景 |
| intent-routing-and-kb-domain-design.md | 意图与知识库方案，部分已实现 |
| rag-module-design.md | 标注未落地，但模块化结构已部分实现 |
| session-memory-python.md | 迁移设计稿，当前代码未完成 |
| code-review-defects-report.md | 2026-08-01 缺陷历史，不代表当前审计 |
| interview-platform-design.md | 未落地模拟面试设计 |
| interview-questions-backend.md | 面试材料，不是接口规范 |
| rag-frontier-and-open-source-fit-2026.md、papers | 研究与论文资料，不是运行依赖 |

需要当前行为时先看本套开发文档和源码；需要设计背景时再读 step/方案文档。任何文件标注「设计稿」时，不应从其中的示例代码推导线上能力。
