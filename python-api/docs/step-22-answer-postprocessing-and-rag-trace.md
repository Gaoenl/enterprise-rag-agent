# Step 22：回答后处理、引用校验与 RAG Trace

## 1. 本步骤目标

Step 21 已经保证模型上下文和 citations 一致。Step 22 在模型生成之后增加回答校验，并记录一次 RAG 请求从进入到结束的完整执行轨迹。

```text
User Query
  -> Query Resolve
  -> Route
  -> Knowledge Base Select
  -> Query Rewrite
  -> Hybrid Retrieve
  -> RRF
  -> Rerank
  -> Context Pack
  -> LLM Generate
  -> Answer Post-process
  -> Final Answer
       |
       -> RAG Trace
```

## 2. Trace 是什么

Trace 是一次请求的结构化执行记录。它不仅说明“请求成功或失败”，还记录请求经过了哪些节点、每个节点用了多长时间、输入输出摘要以及在哪一步发生异常。

例如：

```text
trace_id: 337000000000000001
status: SUCCESS
total_latency: 1860 ms

节点：
1. query_resolve       80 ms
2. route               2 ms
3. kb_select           12 ms
4. query_rewrite      110 ms
5. hybrid_retrieve    160 ms
6. rerank             240 ms
7. context_pack         1 ms
8. llm_generate      1200 ms
9. post_process         3 ms
```

## 3. Trace、日志和会话历史的区别

### 日志

日志面向开发和运维，通常是离散文本：

```text
Rerank completed, final_count=8
```

它适合快速排错，但不容易完整还原单次 RAG 请求。

### 会话历史

`chat_conversation` 和 `chat_message` 保存用户看得到的对话：

```text
用户问了什么
助手回答了什么
引用了哪些分片
```

它不应该保存所有内部节点和技术参数。

### RAG Trace

`rag_trace` 保存模型背后的执行过程：

```text
问题是否被改写
为什么进入 RAG
选择了哪个知识库
向量和关键词召回了多少分片
Rerank 前后排名如何变化
上下文是否被截断
模型耗时和 Token 用量
哪一个节点失败
```

三者需要同时存在，不能互相替代。

## 4. 没有 Trace 会出现什么问题

系统没有 Trace 仍然可以回答问题，但会逐渐成为不可解释的黑盒。

### 无法定位错误回答的原因

回答错误可能来自：

- 问题独立化错误。
- 路由错误，没有进入 RAG。
- 选择了错误知识库。
- Embedding 召回不到正确分片。
- 关键词提取错误。
- RRF 排序不合理。
- Rerank 把正确分片排到后面。
- Context Packing 截掉了重要内容。
- LLM 没有遵守上下文。

如果只保存最终答案，无法知道问题发生在哪一步。

### 无法进行检索效果评估

无法统计：

- Vector Recall 是否有效。
- Keyword Recall 是否补充了向量结果。
- Rerank 是否提升排序。
- 哪些查询经常没有召回结果。
- 哪个知识库的回答质量较差。

### 无法分析性能

只能知道接口整体很慢，却不知道时间消耗在：

```text
Embedding
PostgreSQL
Rerank
LLM
```

### 无法统计模型成本

如果不保存 Token 用量和模型信息，就无法按租户、用户或模型统计调用成本。

### 无法关联用户反馈

用户给某条回答差评时，只能看到答案，无法恢复当时使用的查询、候选分片、模型和参数。

### 无法满足企业审计

企业环境通常需要回答：

```text
这条回答使用了哪些资料？
当时使用的模型是什么？
为什么选择这个知识库？
是否跨租户读取了数据？
```

没有 Trace 很难提供可核查证据。

## 5. Java 与 Python 的职责

继续遵守项目边界：

### Java

- 生成全链路 Trace ID。
- 将 Trace ID 传给 Python。
- 保存 `rag_trace`。
- 将助手消息的 `trace_id` 关联到 Trace。
- 提供 Trace 查询接口和租户权限控制。

### Python

- 接收 Trace ID。
- 记录 RAG 内部节点。
- 记录每个节点耗时、状态和输出摘要。
- 记录模型、Token 用量和检索统计。
- 将完整 Trace 数据返回 Java。

Python 不直接写 `rag_trace`，避免业务表出现双写所有权。

## 6. Trace ID 设计

建议 Java 在调用 Python 前生成数据库主键：

```text
traceId: Long
```

请求结构增加：

```json
{
  "traceId": 337000000000000001,
  "conversationId": 336000000000000001,
  "tenantId": 331372985380245504,
  "userId": 63,
  "question": "公司的差旅住宿费上限是多少？"
}
```

Python 原样返回该 Trace ID。

HTTP 请求级关联 ID 可以继续使用 `request_id VARCHAR(128)`。`trace_id` 负责关联数据库记录，`request_id` 负责关联 Java 和 Python 日志。

## 7. Trace 节点模型

```python
class TraceNode:
    name: str
    status: str
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    input_summary: dict
    output_summary: dict
    error_message: str | None
```

第一版节点：

```text
QUERY_RESOLVE
QUERY_ROUTE
KNOWLEDGE_BASE_SELECT
RETRIEVAL_QUERY_REWRITE
VECTOR_RETRIEVE
KEYWORD_RETRIEVE
RRF_FUSION
RERANK
CONTEXT_PACK
LLM_GENERATE
ANSWER_POST_PROCESS
```

HybridRetriever 内部有多个子阶段，后续可通过 TraceRecorder 在组件内部记录，而不是只记录一个总的 `HYBRID_RETRIEVE`。

## 8. Trace 根对象

```python
class RagTraceData:
    trace_id: int
    request_id: str | None
    trace_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    latency_ms: int | None
    input: dict
    output: dict
    nodes: list[TraceNode]
    error_message: str | None
    token_usage: dict
```

状态建议：

```text
RUNNING
SUCCESS
FAILED
DEGRADED
```

例如 Rerank 失败但成功降级到 RRF，最终请求成功，Trace 状态可以标记为：

```text
DEGRADED
```

## 9. TraceRecorder

Python 增加轻量 `TraceRecorder`：

```text
start_node(name, input_summary)
finish_node(name, output_summary)
fail_node(name, exception)
mark_degraded(reason)
finish(output)
fail(exception)
```

建议支持上下文管理器：

```python
with recorder.node("RERANK", input_summary={...}) as node:
    documents = rerank_service.rerank(...)
    node.output_summary = {
        "result_count": len(documents)
    }
```

上下文管理器可以确保异常时仍然记录节点耗时和失败信息。

## 10. Trace 中应该记录什么

建议记录摘要：

```json
{
  "route": {
    "intent": "RAG_QA",
    "needRag": true
  },
  "retrieval": {
    "vectorCount": 30,
    "keywordCount": 12,
    "fusionCount": 20,
    "rerankCount": 8
  },
  "context": {
    "documentCount": 5,
    "totalChars": 11240,
    "truncated": true
  },
  "model": {
    "llm": "qwen-plus",
    "embedding": "text-embedding-v4",
    "rerank": "qwen3-rerank"
  }
}
```

## 11. Trace 中不应该直接记录什么

默认不要完整保存：

- API Key。
- 数据库密码。
- Authorization Header。
- 完整系统 Prompt。
- 全量文档正文。
- 超长用户输入。
- 不必要的个人敏感信息。

Trace 记录分片 ID、文档 ID、排名、分数和内容摘要即可。完整内容已经存在业务表中，可以通过权限受控的 ID 查询。

## 12. 回答后处理

模型生成后增加 `AnswerPostProcessor`：

```text
原始回答
  -> 去除首尾空白
  -> 解析 [来源 N]
  -> 校验引用编号
  -> 删除或标记无效引用
  -> 统计实际使用的引用
  -> 设置回答状态
  -> 输出最终回答
```

## 13. 引用校验

假设实际上下文只有：

```text
[来源 1]
[来源 2]
[来源 3]
```

模型却输出：

```text
根据制度，住宿费上限是 500 元。[来源 7]
```

`来源 7` 是无效引用。后处理器需要识别：

```python
pattern = r"\[来源\s*(\d+)]"
```

第一版策略：

- 保留有效引用。
- 删除无效引用标记。
- 在 Trace 中记录 `invalidCitationIndexes`。
- 不因为单个无效引用导致整个请求失败。

后续可以增加更严格模式：发现无效引用时重新生成一次回答。

## 14. 回答状态

建议返回：

```text
ANSWERED       有知识库依据并完成回答
NO_EVIDENCE    RAG 没有有效上下文
PARTIAL        只找到部分依据
GENERAL        普通聊天
FAILED         生成失败
```

第一版可以可靠判断：

```text
普通聊天                  -> GENERAL
RAG 无上下文              -> NO_EVIDENCE
RAG 有上下文且生成成功     -> ANSWERED
```

`PARTIAL` 暂时不要只依赖字符串猜测，后续可通过结构化模型输出实现。

## 15. Token Usage

LangChain `AIMessage` 可能提供：

```python
response.usage_metadata
```

常见字段：

```json
{
  "input_tokens": 1500,
  "output_tokens": 300,
  "total_tokens": 1800
}
```

不同 Provider 也可能把用量放在：

```python
response.response_metadata["token_usage"]
```

LlmClient 应统一转换为项目自己的 `TokenUsage`，不要让 Provider 字段直接扩散到业务层。

## 16. Chat 响应调整

Python `ChatData` 建议增加：

```text
traceId
answerStatus
usedCitationIndexes
invalidCitationIndexes
tokenUsage
trace
```

开发阶段可以返回完整 Trace；生产环境面向普通前端时只返回 `traceId`，完整 Trace 通过受权限保护的诊断接口查询。

## 17. Java 持久化流程

```text
1. Java 生成 traceId
2. Java 将 traceId 传给 Python
3. Python 返回 answer + trace
4. Java 保存 rag_trace
5. Java 保存 ASSISTANT chat_message
6. chat_message.trace_id = rag_trace.id
7. Java 返回 ChatResponse
```

如果 Python 调用失败，Java 仍应保存一条 `FAILED` Trace，记录远程错误和总耗时。

## 18. 与现有 rag_trace 表的映射

现有字段可以映射：

| 数据 | rag_trace 字段 |
|---|---|
| Java 生成的 Trace ID | `id` |
| 当前租户 | `tenant_id` |
| 当前会话 | `conversation_id` |
| 助手消息 | `message_id` |
| `CHAT_QA` | `trace_type` |
| HTTP 请求关联 ID | `request_id` |
| 问题、知识库、模型摘要 | `input` |
| 回答状态、引用和 Token | `output` |
| Python 节点列表 | `nodes` |
| 总耗时 | `latency_ms` |
| SUCCESS/FAILED/DEGRADED | `status` |
| 异常摘要 | `error_message` |

现有表结构足够第一版使用，暂时不需要新增表。

## 19. 文件规划

Python：

```text
python-api/app/
├─ schemas/
│  ├─ trace_schema.py
│  └─ answer_schema.py
├─ trace/
│  ├─ __init__.py
│  └─ trace_recorder.py
├─ postprocessors/
│  ├─ __init__.py
│  └─ answer_postprocessor.py
├─ clients/
│  └─ llm_client.py
└─ services/
   └─ chat_service.py
```

Java：

```text
java-api/src/main/java/com/example/rag/trace/
├─ entity/RagTrace.java
├─ mapper/RagTraceMapper.java
├─ service/RagTraceService.java
└─ service/impl/RagTraceServiceImpl.java
```

业务代码只在对话中提供草稿，不由 Codex 写入项目。

## 20. 开发顺序

1. 定义 `TraceNode` 和 `RagTraceData`。
2. 实现 `TraceRecorder`。
3. 定义回答后处理结果。
4. 实现引用编号解析和校验。
5. LlmClient 返回答案和统一 Token Usage。
6. ChatService 为每个主要节点记录 Trace。
7. Python ChatData 返回 Trace。
8. Java 增加 RagTrace Entity、Mapper 和 Service。
9. Java 调 Python 前生成 Trace ID。
10. Java 保存 Trace 并关联助手消息。
11. 增加 Trace 查询接口。
12. 添加单元测试和失败降级测试。

## 21. 测试范围

至少覆盖：

1. 成功请求生成完整 Trace。
2. 每个节点记录耗时。
3. 节点异常记录 FAILED。
4. Rerank 降级后 Trace 为 DEGRADED。
5. 无效引用编号被识别。
6. 有效引用编号被保留。
7. RAG 无上下文返回 NO_EVIDENCE。
8. 普通聊天返回 GENERAL。
9. Token Usage 正确归一化。
10. Python 失败时 Java 仍保存 FAILED Trace。
11. Trace 与助手消息正确关联。
12. 不同租户不能查询对方 Trace。

## 22. 验收标准

- 每次 Chat 请求都有唯一 Trace ID。
- Python 能记录主要 RAG 节点及耗时。
- 回答中的引用编号经过有效性校验。
- 响应能够返回回答状态和 Token Usage。
- Java 能将 Trace 保存到现有 `rag_trace`。
- 助手消息能够关联 `trace_id`。
- Rerank 等可降级节点失败时 Trace 标记为 DEGRADED。
- Trace 不保存密钥和不必要的完整敏感正文。
