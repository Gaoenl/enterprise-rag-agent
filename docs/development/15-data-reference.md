# 数据结构参考

[返回目录](README.md)

## 数据库基线字段

下表列出 V1 基线字段，后续迁移字段在下一节。约束、默认值和索引以 SQL 为最终依据。

| 表 | 字段 |
| --- | --- |
| sys_tenant | id, tenant_code, tenant_name, status, description, created_at, updated_at, deleted |
| sys_user | id, tenant_id, username, display_name, email, role_code, status, created_at, updated_at, deleted |
| kb_knowledge_base | id, tenant_id, name, description, visibility, embedding_model_config_id, chunk_strategy JSONB, status, created_by, created_at, updated_at, deleted |
| kb_document | id, tenant_id, knowledge_base_id, file_name, file_type, file_uri, file_size, content_hash, parse_status, metadata JSONB, created_by, created_at, updated_at, deleted |
| kb_document_chunk | id, tenant_id, knowledge_base_id, document_id, chunk_index, content, token_count, embedding vector(1536), embedding_model, metadata JSONB, created_at, updated_at, deleted |
| ingestion_task | id, tenant_id, knowledge_base_id, document_id, task_type, status, progress, error_message, started_at, finished_at, created_by, created_at, updated_at |
| ingestion_task_step | id, task_id, step_name, status, input JSONB, output JSONB, error_message, started_at, finished_at, created_at, updated_at |
| chat_conversation | id, tenant_id, user_id, knowledge_base_id, title, channel, metadata JSONB, created_at, updated_at, deleted |
| chat_message | id, tenant_id, conversation_id, parent_message_id, role, content, citations JSONB, token_usage JSONB, trace_id, created_at, deleted |
| model_provider | id, tenant_id?, provider_code, provider_name, endpoint, auth_type, status, created_at, updated_at, deleted |
| model_config | id, tenant_id?, provider_id, model_code, model_name, model_type, parameters JSONB, is_default, status, created_at, updated_at, deleted |
| rag_trace | id, tenant_id, conversation_id?, message_id?, trace_type, request_id, input/output/nodes JSONB, latency_ms, status, error_message, created_at, updated_at |
| rag_feedback | id, tenant_id, conversation_id?, message_id?, user_id?, rating, feedback_type, comment, metadata JSONB, created_at |

带 tenant_id 的业务表必须把租户条件放入读取、更新和删除路径；只通过父表间接关联仍需检查父资源归属。

## 增量结构

| 迁移 | 字段/结构 |
| --- | --- |
| V3/V6 | sys_user.password_hash, token_version, last_login_at, password_changed_at |
| V4 | auth_refresh_token：id, user_id, token_hash, expires_at, revoked_at, replaced_by_token_id, created_at, created_ip, user_agent |
| V5 | rag_trace.token_usage, degraded_reasons, started_at, finished_at |
| V7 | ingestion_task_step.step_code；任务/步骤唯一和查询索引 |
| V9 | kb_knowledge_base.document_count |
| V10 | 有效文档 `(tenant_id, knowledge_base_id, content_hash)` 部分唯一索引 |
| V12 | ingestion_task.pipeline_config JSONB |
| V15 | kb_document_chunk.embedding_dimension |
| V16 | kb_knowledge_base.domain_code，默认 GENERAL |
| V17 | chat_conversation.summary, last_summary_message_id |
| V18 | chat_conversation.last_route JSONB |
| V19 | chat_conversation/chat_message ID 序列默认值；没有 chat_turn |

V1 的知识库外键 embedding_model_config_id 通过后续 ALTER 添加，完整定义请直接阅读 V1。索引包括向量 HNSW、Chunk 文本 GIN/trgm、租户/知识库/删除组合、入库状态/时间、会话消息和运行中会话 Trace。

## 统一传输结构

Java ApiResult：`success, code, message, data, timestamp`。Python ApiResult：`success, code, message, data`。PageResult：`records, total, pageNo, pageSize`。前端自动解包 data；调试网络响应时要看原始外层。

Java 对外 ChatRequest：`conversationId?, knowledgeBaseId?, question, model?`。可信 tenant/user/request/trace 由服务端补充。Python 当前 ChatRequest：`question, conversationId?, tenantId, userId, knowledgeBaseId?, traceId, requestId, model?`，缺少 ChatService 仍读取的 history/summary/lastRoute。

Python ChatData 当前声明：`conversationId, traceId, question, standaloneQuery, answer, model, mode, intent, needRag, knowledgeBaseId?, routeReason?, citations[], answerStatus, usedCitationIndexes[], invalidCitationIndexes[], tokenUsage, trace?`。

AnswerStatus 的精确枚举以 `answer_schema.py` 为准；调用方至少区分正常、无依据、需要澄清及引用后处理结果，不把 HTTP 200 一律视为有答案。

## Embedding 与检索结构

EmbeddingRequest：`texts[]` 至少 1 条，`model?`；EmbeddingData：`model, dimension, items[]`；Item：`index, embedding[]`。index 用于批次顺序对齐，不能依赖响应数组偶然顺序替代校验。

RetrievalDebugRequest：`requestId?, tenantId, userId, knowledgeBaseId?, question(1..4000), mode(VECTOR/KEYWORD/HYBRID), enableRewrite, enableRerank, enableMultiQuery, vectorTopK(1..100)?, keywordTopK(1..100)?, fusionTopK(1..100)?, finalTopK(1..50)?, rrfK(1..1000)?, vectorWeight/keywordWeight(0..10)?`。

候选字段：`chunkId, documentId, knowledgeBaseId, chunkIndex, documentName?, content, vector/keyword/fusion/rerankScore?, 对应 rank?, retrievalSources[], metadata, citationIndex?, contextTruncated`。响应另有 originalQuery、semanticQuery、keywords、alternativeQueries、vectorMergedCount、开关状态、degraded、四阶段数组、packedContext、timings 和 warnings。

内部 RetrievalCandidate 还记录 embedding_model、embedding_dimension。PackedContext 为 text、documents、total_chars、truncated。

## 路由、Trace 与 SSE

RouteDecision：`intent, need_rag, confidence, reason, domain, tool?, router_path, inherit_context, source_scores, intent_confidence`。ToolRequest：`tool, tool_input`。ResolvedQuery：`original_query, standalone_query, rewritten, reason?`。RetrievalQuery：`semantic_query, keywords[], synonym_keywords[], alternative_queries[]`。

TokenUsage：`inputTokens, outputTokens, totalTokens`。TraceNode：名称、状态、起止时间、耗时、输入/输出摘要、错误。RagTraceData：traceId、requestId、类型、状态、起止/耗时、input/output、nodes、tokenUsage、errorMessage、degradedReasons。

SSE 数据通过事件名解释，见 [聊天文档](06-chat-memory-streaming.md)。delta.data.content 是草稿；final.data 是最终 ChatData；done 只是传输结束信号。

## 评测结构

EvaluationCreateRequest：`tenantId, userId, knowledgeBaseId, datasetCode(default CRUD_RAG_V1), experiments[](至少一项), vectorWeight/keywordWeight(0..10)`。九个 experiments 见 [测评文档](09-evaluation-observability.md)。

EvaluationRunData：runId、status、datasetCode、knowledgeBaseId、totalCases/completedCases/progress、currentExperiment、errorMessage、createdAt/finishedAt。ResultData：runId、status、summaries、details。作业数据只在内存，不是数据库实体。

## 入库配置 JSON

KnowledgeBase.chunk_strategy 与 IngestionTask.pipeline_config 使用：`chunkType, chunkSize, chunkOverlap, embeddingModel?, embeddingDimension?, embeddingBatchSize?`。任务字段是创建时快照。Chunk metadata、文档 metadata 和 Trace JSON 属于松结构；新增 key 要保持向后兼容并在读取端提供缺省。

源码：[V1](../../java-api/src/main/resources/db/migration/V1__init_pg_schema.sql)、[全部迁移](../../java-api/src/main/resources/db/migration)、[Python schemas](../../python-api/app/schemas)、[RAG schemas](../../python-api/app/rag/schemas)、[Java DTO 根目录](../../java-api/src/main/java/com/example/rag)。
