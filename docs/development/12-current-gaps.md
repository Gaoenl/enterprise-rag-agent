# 当前差异、迁移阻塞与限制

[返回目录](README.md)

> 静态核对结果，2026-09-09。以下问题不是本次文档修改引入；本次没有修复业务代码，也没有声称复现了每个运行时错误。

## 聊天迁移阻塞

| 证据 | 当前影响 |
| --- | --- |
| schemas/chat_schema.py 的 ChatRequest 没有 history/summary/last_route；apps/chat/chat_service.py 仍读取 | 验证或转换请求时可能 AttributeError，旧链路不兼容 |
| ChatData 必填 conversation_id；ChatService 两个组装分支未传入 | 前述问题修复后仍可能出现响应模型校验失败 |
| memory/postgres_store.py 的 create_turn/complete_turn/fail_turn 位于 load_snapshot 内部 return 后 | 不成为实例方法，协议未实现完整 |
| 新存储 SQL 引用 chat_turn，现有迁移未建表 | 轮次持久化尚无数据库基础 |
| ChatService 未注入 ConversationStore；Engine.with_memory 仅赋值 | Python 会话记忆尚未接通 |
| V19 为聊天 ID 添加序列，但 Java 仍写消息/会话 | 必须协调唯一写入方，不能仅执行 SQL 宣告迁移完成 |

这些文件包含用户已有工作区修改。修复时需统一端到端所有权和契约，不能单独恢复一个字段后就把其余缺口忽略。

## 配置与能力差异

| 项目 | 实现事实 | 文档/操作应如何理解 |
| --- | --- | --- |
| Redis | Cache 读取 rag.redis.enabled，默认 false；YAML 写 rag.security.redis | YAML 中 enabled:true 不表示实际开启 |
| 摘要 | Properties 绑定 rag.summary；YAML 写 rag.security.summary | Java 类默认生效，YAML 修改未必生效 |
| 关键词 | ILIKE + pg_trgm + 命中加权 | 不是 BM25 |
| Embedding mock | 实际创建 OpenAIEmbeddings，无 mock 分支 | 需要真实模型配置/测试替身 |
| 模型管理 | Python 主要读环境，聊天要求 model 等于 LLM_MODEL | 数据库新增模型不等于即时可调用 |
| 向量维度 | 列仍是 vector(1536)，V15 只增加标记 | 不支持任意维度混存 |
| Embedding HTTP | Schema 只有 texts/model | 任务维度字段不等于已跨 HTTP 传递 |
| Java health | 放行 /api/health，但无对应 Controller | 使用 /actuator/health |
| Java Swagger | 放行路径，未发现对应依赖/控制器 | 不承诺已有页面 |
| Compose | 仅 PostgreSQL | Redis、S3、应用部署需另备 |
| 前端 /admin/retrieval | 注册 RagEvaluationPage | RetrievalDebugPage 不等于已注册调试路由 |

## 摘要与可插拔入口待验证项

ConversationSummaryService 的 gap 计算为消息数量减 last_summary_message_id，而该字段是消息 ID，不是数量；Snowflake 下不能解释为新增消息数。首次摘要 lastPos=null 时条件更新的空值语义也应回归。compressSafely 内部直接调用带 @Transactional 的 compress，不能仅凭注解断言经过 Spring 事务代理。

RagEngine.retrieve 接收 final_top_k 但未传给底层；with_memory 没有实际加载调用。ChatData 不输出完整 RouteDecision，而 Java 有读取/更新 route 的逻辑，多轮路由落库也需端到端核对。

这些是静态证据支持的验证重点，不在本文扩大成已完成的全面代码审计。

## 工程化边界

- 入库使用进程内事件/线程池，缺少持久消息和崩溃恢复保证。
- 测评作业状态在进程内，重启丢失，不支持无条件多 worker 扩容。
- Python API 未接入 Java 等价 JWT 校验，依赖内部网络信任。
- 没有 Java src/test；前端没有 test 脚本；现有 Python 测试不代表整链路覆盖。
- 部分 Python 依赖未锁版本；字节码文件出现在工作区变更中，需与业务提交分开审查。
- V3_auth.sql 不符合默认 Flyway 版本脚本命名，实际迁移历史须核对；V6 补齐认证字段。
- Actuator 指标公开，未形成 Prometheus/Grafana/OTel 完整部署。

## 设计稿与未接入能力

模拟面试、简历/媒体业务、MCP、Milvus、OCR/视觉解析、完整资源配额限流是方案或路线图，不是当前产品能力。rag_feedback 有表但未找到完整业务接口；工具注册只有 calculator，web_search 是 Schema 示例。

历史 Python README 仍写 Step 12A，根 README 的目录和「18 版迁移」「BM25」「Redis 已开启」等描述不能作为当前事实。rag-module-design 标注未落地，但 rag/engine 和 apps 结构已经部分实现；session-memory-python 则仍处迁移状态。使用本文档区分「已有代码」「当前不兼容」「未来设计」。

## 如何关闭本清单

每项关闭需有代码变更、配置生效或运行验证证据，并同步更新相应章节。聊天迁移至少验收同步/SSE、旧会话、失败重试、并发、唯一写入与摘要；不能只用编译通过替代。
