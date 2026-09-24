# Step 20：Cross Encoder Rerank 精排

## 1. 本步骤目标

Step 19 已经通过向量检索、关键词检索和 RRF 融合获得候选分片。本步骤在候选召回之后增加 Rerank：

```text
问题独立化
  -> 检索查询改写
  -> 向量 Top30 + 关键词 Top30
  -> RRF 融合 Top20
  -> Rerank 精排 Top8
  -> Context Packing
  -> LLM Generation
```

RRF 负责融合不同召回信号；Rerank 模型负责判断每个候选分片是否真正能够回答当前问题。

## 2. Rerank 与向量检索的区别

向量检索分别计算问题和文档的 Embedding，再比较两个向量，速度快，适合从大量分片中召回候选。

Cross Encoder 将问题与单个候选分片一起输入排序模型：

```text
query: 用户问题
document: 候选分片
```

模型可以读取二者之间更细致的语义关系，因此排序准确性通常更高，但计算成本也更高。它只适合处理召回后的少量候选，不能替代第一阶段的大规模检索。

## 3. 组件职责

```text
HybridRetriever
  -> 只负责向量、关键词和 RRF

RerankClient
  -> 只负责调用外部排序 API

RerankService
  -> 负责候选映射、截断、精排和失败降级

ChatService
  -> 编排 Retrieve -> Rerank -> Context Pack
```

Rerank 不直接写入 `HybridRetriever`，以便后续独立开关、替换模型和记录耗时。

## 4. 模型选择

当前阿里云百炼文本排序模型包括 `qwen3-rerank` 和 `gte-rerank-v2`。本项目第一版建议使用：

```text
qwen3-rerank
```

原因：

- 面向文本语义检索和 RAG。
- 支持中文。
- 支持自定义排序任务说明。
- 新项目不再优先选择旧的 gte-rerank 系列。

官方接口说明：

```text
https://help.aliyun.com/zh/model-studio/text-rerank-api
```

`qwen3-rerank` 和 `gte-rerank-v2` 的请求及响应结构不同。本步骤第一版只实现 `qwen3-rerank`，后续通过统一 Client 接口扩展其他 Provider。

## 5. API 配置

建议环境变量：

```dotenv
RERANK_ENABLED=true
RERANK_PROVIDER=dashscope_qwen3
RERANK_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-api/v1/reranks
RERANK_API_KEY=sk-xxxx
RERANK_MODEL=qwen3-rerank
RERANK_CANDIDATE_TOP_K=20
RERANK_FINAL_TOP_K=8
RERANK_MAX_DOCUMENT_CHARS=6000
RERANK_TIMEOUT_SECONDS=30
```

`RERANK_BASE_URL` 使用完整接口地址。这样代码不需要理解 Workspace ID 和地域 URL 的拼接规则。

API Key 必须通过环境变量提供，不写入代码和 Git。

## 6. qwen3-rerank 请求

```json
{
  "model": "qwen3-rerank",
  "query": "公司的差旅住宿费报销上限是多少？",
  "documents": [
    "候选分片一",
    "候选分片二"
  ],
  "top_n": 8,
  "instruct": "Given an enterprise knowledge-base question, rank passages by whether they provide direct evidence for answering the question."
}
```

响应中的 `index` 指向原始 `documents` 数组位置：

```json
{
  "results": [
    {
      "index": 1,
      "relevance_score": 0.93
    }
  ]
}
```

不能根据返回顺序猜测原文，必须通过 `index` 映射回原始 LangChain `Document`。

## 7. 数据模型

```text
RerankItem
├─ index
└─ relevance_score

RerankData
├─ model
├─ items
└─ total_tokens
```

Rerank 完成后在 `Document.metadata` 中增加：

```text
rerank_score
rerank_rank
```

原有字段继续保留：

```text
fusion_score
vector_score
keyword_score
vector_rank
keyword_rank
retrieval_sources
```

## 8. 候选数量

Step 19 的 `RETRIEVAL_FINAL_TOP_K` 原本直接返回 8 条。加入 Rerank 后需要给精排更多候选：

```dotenv
RETRIEVAL_FUSION_TOP_K=20
RERANK_FINAL_TOP_K=8
```

RRF 输出 20 条，Rerank 从中选择 8 条。候选太少会限制 Rerank 的提升空间；候选过多会增加调用成本和延迟。

## 9. 文档截断

单个分片通常不会达到排序模型上限，但仍需防止异常长文本：

```text
RERANK_MAX_DOCUMENT_CHARS=6000
```

第一版按字符数截断，用于保护接口。后续可以使用模型对应 tokenizer 按 Token 精确截断。

截断只影响发送给 Rerank 的文本，不修改数据库分片，也不修改最终进入 Context Packing 的原文。

## 10. 失败降级

Rerank 是质量增强步骤，失败不能让整个 RAG 请求失败：

```text
RERANK_ENABLED=false
  -> 使用 RRF 前 N 条

API 超时或非 2xx
  -> 记录错误
  -> 使用 RRF 前 N 条

响应 JSON 无效
  -> 记录错误
  -> 使用 RRF 前 N 条

返回 index 越界
  -> 跳过异常项

所有返回项都无效
  -> 使用 RRF 前 N 条
```

降级结果必须保留 `fusion_score`，并将 `rerank_score` 留空。

## 11. 安全和数据边界

- 只向排序模型发送已通过租户和知识库过滤的候选分片。
- 不发送用户身份、租户名称、数据库连接信息和 API Key。
- 日志不打印完整候选分片和密钥。
- 云端 Rerank 会接触候选文本，生产部署前需要确认企业数据合规要求。
- 对高敏感数据可以实现本地 BGE Reranker Provider。

## 12. ChatService 编排

```text
retrieval_query = RetrievalQueryRewriter.rewrite(...)

retrieved_documents = HybridRetriever.retrieve(...)

reranked_documents = RerankService.rerank(
    query=standalone_query,
    documents=retrieved_documents
)

context = ContextPacker.pack(reranked_documents)

answer = LlmClient.chat(...)
```

用于 Rerank 的问题建议采用 `standalone_query`，因为它保留完整用户意图；用于向量召回的 `semantic_query` 可能经过关键词化或口语清理。

## 13. 引用信息

前端引用增加：

```json
{
  "chunkId": 10001,
  "documentName": "差旅管理制度.pdf",
  "fusionScore": 0.0315,
  "rerankScore": 0.934,
  "rerankRank": 1,
  "retrievalSources": ["vector", "keyword"]
}
```

开发阶段保留完整检索和精排字段，便于比较 RRF 与 Rerank 的排序变化。

## 14. 测试范围

至少覆盖：

1. Rerank 返回的 index 能映射回正确文档。
2. 结果按模型返回顺序排列。
3. `rerank_score` 和 `rerank_rank` 正确写入 metadata。
4. `top_n` 大于候选数量时自动缩小。
5. 候选为空时不调用外部 API。
6. Rerank 禁用时使用 RRF 顺序。
7. API 异常时降级使用 RRF 顺序。
8. 无效或越界 index 不导致请求失败。
9. 候选文本截断不修改原始 Document。

## 15. 验收标准

- RRF 输出候选数量提升到 20。
- Rerank API 能接收问题和候选分片。
- 返回 index 能正确映射到原始分片。
- 最终只保留 Top8。
- 引用中包含 RRF 和 Rerank 排名信息。
- 关闭 Rerank 后原有 RAG 流程仍能工作。
- Rerank 超时或失败时能够自动降级。

## 16. 后续步骤

Step 21 将围绕 Context Packing 与 Prompt Construction 优化，包括去重、邻接分片扩展、上下文预算、引用编号和无答案约束。
