# 聊天、SSE 与会话记忆

[返回目录](README.md)

## 当前所有权

Java ChatServiceImpl 仍负责读取/创建会话、读取近期消息、保存用户消息、组装 Python 请求、接收回答、写助手消息和 Trace。流式成功结果由 ChatPersistenceService 保存。Python ChatService 负责请求转换、调用 RagEngine 与生成 SSE。

当前工作区的 Python ChatRequest 已去掉 history/summary/last_route，而 ChatService 仍访问这些字段；ChatData 新增必填 conversationId，但组装没有提供。以下流程说明现有调用意图，不能据此认为当前聊天链路已经可运行。详见 [阻塞清单](12-current-gaps.md)。

## 对外与内部契约

浏览器提交 question、可选 conversationId、knowledgeBaseId、model，不自行决定 tenantId/userId/traceId。Java 注入可信身份及跟踪字段。同步接口 `/api/chat/completions` 返回统一 JSON；流式 `/api/chat/stream` 返回 text/event-stream。

内部 ChatRequest 的真实声明见 [数据参考](15-data-reference.md)。Java 客户端 DTO 仍携带历史/摘要；迁移时需在「Java 提供记忆」与「Python 自己加载记忆」间完整切换，不能只删字段。

## SSE 协议

| 事件 | 含义 | 消费方式 |
| --- | --- | --- |
| start | traceId/conversationId 等开始信息 | 建立本轮状态 |
| route | intent/needRag/knowledgeBaseId | 展示路由 |
| retrieval | 候选、重排、上下文数量 | 可选检索进度 |
| delta | content 文本增量 | 追加草稿 |
| final | 完整回答、状态、引用和统计 | 替换/确认最终内容 |
| error | code/message/traceId | 标记失败 |
| done | 流结束 | 清理读取状态，不等于成功 |
| heartbeat | Java 流转发支持的保活事件 | 不作为回答文本 |

常见成功序列为 start → route → retrieval（可选）→ delta* → final → done。无依据或澄清可能没有 delta；错误序列可能为 start → … → error → done。SSE 帧用空行分隔，data 是 JSON，传输分片边界不等于事件边界。

浏览器使用 fetch POST 与 Authorization，不能直接换成不支持同等请求契约的原生 EventSource。请求由 AbortSignal 取消。Python 设置 Cache-Control:no-cache 与 X-Accel-Buffering:no，部署代理仍需关闭响应缓冲。

## Java 流处理与持久化

PythonSseEventParser 解析上游事件，ChatStreamExecutor 承担长连接工作，SseEmitterSender 管理发送/关闭。start/route/retrieval/delta/heartbeat 可转发；final 关联持久化，异常、超时、客户端断开记录失败和关闭原因。

流结束但没有保存 final 会作为异常路径处理。客户端提前断开并不等于数据库中没有用户消息；重试前应核对会话历史。UI 应区分取消、服务端错误、缺失 final 和正常完成，避免把部分草稿当作成功回答。

## Java 记忆与摘要

ConversationMemoryCache 使用工作记忆列表 `wm:<conversationId>`，缓存 TTL 为 86400 秒，并维护摘要。读取近期历史可回退数据库；成功消息更新缓存，摘要后裁剪近期列表。

ConversationSummaryService 在提交后异步触发压缩，结合消息数和估算 Token 阈值调用 Python summarize，再条件更新 summary 和 last_summary_message_id。默认字段为 countThreshold=15、tokenThreshold=2000、gapCount=5、gapTokens=500、keepRecent=10；Token 为字符估算，不是模型 tokenizer 实测。

配置类读取 rag.summary，缓存读取 rag.redis.enabled，而 YAML 放在 rag.security.summary/redis 下，不能假定 YAML 的 true 已经启用缓存。摘要条件更新、首次空游标和 gap 计算也需要单独回归，详见限制清单。

## Python 迁移状态

memory/store.py 定义 ConversationStore 协议：创建会话、加载快照、创建轮次、完成/失败轮次。models.py 定义上下文、快照、句柄和结果；postgres_store.py 有部分 SQL，database.py 定义 SQLAlchemy Engine。它们尚未由 ChatService 接入。

当前 postgres_store 的 create_turn/complete_turn/fail_turn 缩进在 load_snapshot 内部，且 return 之后；不是可调用的类方法。它引用 chat_turn，而当前迁移没有创建该表。V19 只为会话/消息 ID 加序列默认值，并增加运行中 Trace 索引。

迁移验收必须覆盖：唯一写入方、旧数据 ID、不重复消息、请求幂等、同会话并发、失败状态、缓存与摘要、SSE final、Java/Python 字段兼容。不能只以迁移 SQL 执行成功判定完成。

源码：[Java ChatService](../../java-api/src/main/java/com/example/rag/chat/service/impl/ChatServiceImpl.java)、[Python ChatService](../../python-api/app/apps/chat/chat_service.py)、[SSE 编码](../../python-api/app/streaming/sse_encoder.py)、[会话存储](../../python-api/app/memory/postgres_store.py)。
