# API 参考

[返回目录](README.md)

## 公共约定

Java 外部基址默认 `http://127.0.0.1:8123`，除 login、refresh、Actuator 公开项外均需 Bearer JWT。Controller 返回 `ApiResult<T>`，SSE 除外。管理员代表 `PLATFORM_ADMIN` 或 `ADMIN`；仅平台管理员会单独标注。Long ID 在前端按字符串处理。

本表按当前全部 Java Controller 和 Python `app/api/*api.py` 核对。字段细节见 [数据参考](15-data-reference.md)，实际校验以源码/运行时响应为准。

## 认证、租户与用户

| 方法与路径 | 权限 | 请求 | data/作用 |
| --- | --- | --- | --- |
| POST /api/auth/login | 公开 | JSON LoginRequest；另采集 IP/User-Agent | TokenResponse |
| POST /api/auth/refresh | 公开 | `{refreshToken}`；另采集 IP/User-Agent | 新 TokenResponse |
| POST /api/auth/logout | 登录 | `{refreshToken}` | 撤销当前刷新令牌 |
| GET /api/auth/me | 登录 | 无 | CurrentUserResponse |
| PUT /api/auth/password | 登录 | ChangePasswordRequest | 修改密码并失效令牌 |
| POST /api/auth/logout-all | 登录 | 无 | 全设备退出 |
| POST /api/tenants | PLATFORM_ADMIN | TenantCreateRequest | SysTenant |
| GET /api/tenants/{tenantId} | PLATFORM_ADMIN | path ID | SysTenant |
| GET /api/tenants/enabled | PLATFORM_ADMIN | 无 | 启用租户列表 |
| PATCH /api/tenants/{tenantId}/disable | PLATFORM_ADMIN | path ID | 禁用 |
| GET /api/users | 管理员 | 无 | 当前权限范围用户列表 |
| POST /api/users | 管理员 | UserCreateRequest | UserResponse |
| GET /api/users/{userId} | 管理员 | path ID | UserResponse |
| GET /api/users/by-username | 管理员 | tenantId, username | UserResponse |
| PATCH /api/users/{userId}/disable | 管理员 | path ID | 禁用 |

## 知识库与文档

| 方法与路径 | 权限 | 请求 | data/作用 |
| --- | --- | --- | --- |
| POST /api/knowledge-bases | 管理员 | KnowledgeBaseCreateRequest | KnowledgeBase |
| GET /api/knowledge-bases | 管理员 | keyword?, pageNo=1, pageSize=20 | PageResult<KnowledgeBase> |
| GET /api/knowledge-bases/{knowledgeBaseId} | 管理员 | path ID | KnowledgeBase |
| PATCH /api/knowledge-bases/{knowledgeBaseId} | 管理员 | KnowledgeBaseUpdateRequest，ID 由路径覆盖 | KnowledgeBase |
| DELETE /api/knowledge-bases/{knowledgeBaseId} | 管理员 | path ID | 逻辑删除 |
| GET /api/chat/knowledge-bases | 登录 | 无 | 可用于聊天的 ChatKnowledgeBaseOption[] |
| POST /api/documents/upload | 管理员 | multipart knowledgeBaseId、`file` 列表、metadata? | KnowledgeDocument[]；异步入库 |
| POST /api/documents | 管理员 | KnowledgeDocumentRegisterRequest | 仅登记元数据 |
| GET /api/documents/{documentId} | 管理员 | path ID | KnowledgeDocument |
| GET /api/documents/by-knowledge-base/{knowledgeBaseId} | 管理员 | path ID | KnowledgeDocument[] |
| PATCH /api/documents/{documentId}/parse-status | 管理员 | parseStatus query | 修改状态 |
| DELETE /api/documents/{documentId} | 管理员 | path ID | 逻辑删除 |
| POST /api/documents/batch-delete | 管理员 | JSON Long[] | 批量逻辑删除 |
| GET /api/documents/{documentId}/chunks | 管理员 | path ID | KnowledgeDocumentChunk[] |

## 入库任务

| 方法与路径 | 权限 | 请求 | data/作用 |
| --- | --- | --- | --- |
| GET /api/ingestion/tasks | 管理员 | IngestionTaskQueryRequest 查询参数 | PageResult<IngestionTaskListResponse> |
| GET /api/ingestion/tasks/{taskId} | 管理员 | path ID | IngestionTaskDetailResponse |
| GET /api/ingestion/tasks/{taskId}/steps | 管理员 | path ID | IngestionTaskStepResponse[] |
| GET /api/ingestion/tasks/by-document/{documentId} | 管理员 | path ID | 最新任务详情 |
| POST /api/ingestion/tasks/{taskId}/retry | 管理员 | FAILED taskId | 异步重试 |
| GET /api/ingestion/tasks/statistics | 管理员 | IngestionTaskStatisticsQuery | 统计 |

路由 `/statistics` 与 `/{taskId}` 同在一个 Controller，Spring 会按可匹配性处理；客户端仍应使用完整路径。

## 聊天与会话

| 方法与路径 | 权限 | 请求 | data/作用 |
| --- | --- | --- | --- |
| POST /api/chat/completions | 登录 | Java ChatRequest | ChatResponse |
| POST /api/chat/stream | 登录 | Java ChatRequest | SSE 事件流 |
| GET /api/chat/conversations | 登录 | keyword?, knowledgeBaseId?, pageNo=1, pageSize=20 | PageResult<ChatConversation> |
| GET /api/chat/conversations/{conversationId} | 登录 | path ID | 会话详情 |
| GET /api/chat/conversations/{conversationId}/messages | 登录 | path ID | ChatMessage[] |
| DELETE /api/chat/conversations/{conversationId} | 登录 | path ID | 删除会话 |

当前聊天契约不兼容，以上为 Java 对外入口声明，不表示已通过运行验证。

## 检索、测评与 Trace

| 方法与路径 | 权限 | 请求 | data/作用 |
| --- | --- | --- | --- |
| POST /api/retrieval/debug | 管理员 | RetrievalDebugRequest | 各检索阶段结果 |
| GET /api/retrieval/config | 管理员 | 无 | Python 默认检索参数 |
| POST /api/evaluations/retrieval | 管理员 | EvaluationCreateRequest | EvaluationRunData |
| GET /api/evaluations/retrieval/{runId} | 管理员 | path ID | 作业进度 |
| GET /api/evaluations/retrieval/{runId}/result | 管理员 | path ID | 汇总与 case 明细 |
| GET /api/rag/traces | 管理员 | RagTraceQueryRequest 查询参数 | PageResult<RagTraceListItem> |
| GET /api/rag/traces/statistics | 管理员 | 无 | RagTraceStatisticsResponse |
| GET /api/rag/traces/{traceId} | 管理员 | path ID | RagTraceResponse |

## 模型

| 方法与路径 | 权限 | 请求 | data/作用 |
| --- | --- | --- | --- |
| POST /api/model-providers | 管理员 | CreateRequest | ModelProvider |
| GET /api/model-providers | 管理员 | keyword?, pageNo=1, pageSize=20 | PageResult<ModelProvider> |
| GET /api/model-providers/{id} | 管理员 | ID | ModelProvider |
| PATCH /api/model-providers/{id} | 管理员 | UpdateRequest | ModelProvider |
| DELETE /api/model-providers/{id} | 管理员 | ID | 删除 |
| GET /api/model-providers/available | 管理员 | 无 | ModelProviderResponse[] |
| POST /api/model-configs | 管理员 | CreateRequest | ModelConfig |
| GET /api/model-configs | 管理员 | providerId?, modelType?, keyword?, pageNo=1, pageSize=20 | PageResult<ModelConfig> |
| GET /api/model-configs/{id} | 管理员 | ID | ModelConfig |
| PATCH /api/model-configs/{id} | 管理员 | UpdateRequest | ModelConfig |
| DELETE /api/model-configs/{id} | 管理员 | ID | 删除 |
| GET /api/models | 登录 | type? | ModelConfigResponse[] |

## Python 内部接口

默认基址 9100，当前无 Java 等价 JWT 校验，仅应内网访问。

| 方法与路径 | 请求/查询 | data/流 |
| --- | --- | --- |
| GET /health | 无 | `{status:"UP"}` |
| POST /api/embeddings | texts[]、model? | model、dimension、items |
| POST /api/chat/completions | Python ChatRequest | ChatData；当前不兼容 |
| POST /api/chat/stream | Python ChatRequest | SSE；当前不兼容 |
| POST /api/conversations/summarize | SummarizeRequest | summary |
| POST /api/retrieval/debug | 内部 RetrievalDebugRequest | RetrievalDebugData |
| GET /api/retrieval/config | 无 | RetrievalConfigData |
| POST /api/evaluations/retrieval | 内部 EvaluationCreateRequest | 作业状态 |
| GET /api/evaluations/retrieval/{run_id} | tenantId、userId | 作业状态 |
| GET /api/evaluations/retrieval/{run_id}/result | tenantId、userId | 结果 |

Python 自定义 RagError 返回 success/code/message；Pydantic 422 和 HTTPException detail 不一定使用相同外层。Java 客户端必须同时处理 HTTP 状态与业务体。

源码：[Java Controllers](../../java-api/src/main/java/com/example/rag)、[Python APIs](../../python-api/app/api)。
