# Step 19：PostgreSQL 混合检索与 RRF 融合

## 1. 目标

在 pgvector 语义检索基础上增加关键词检索，并使用 RRF 融合排名：

```text
Retrieval Query
  ├─ pgvector + HNSW + Cosine
  └─ pg_trgm + GIN + ILIKE
             ↓
        chunk_id 去重
             ↓
          RRF 融合
             ↓
         Final TopK
```

向量检索负责语义召回，关键词检索补充编号、名称、术语和精确短语。

## 2. PostgreSQL 扩展

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

`vector` 保存和检索 Embedding；`pg_trgm` 对文本建立三字符片段索引，用于加速 `LIKE`、`ILIKE` 和模糊匹配。

关键词索引：

```sql
CREATE INDEX IF NOT EXISTS idx_chunk_content_trgm
ON kb_document_chunk
USING gin (content gin_trgm_ops)
WHERE deleted = false;
```

当前关键词检索不是严格 BM25。`pg_trgm` 不理解中文词义，只提供字符片段和包含匹配。

## 3. 检索查询

查询改写器输出：

```json
{
  "semanticQuery": "公司差旅制度中的住宿费报销上限",
  "keywords": ["差旅", "住宿费", "报销上限"],
  "alternativeQueries": []
}
```

`semanticQuery` 用于 Query Embedding；`keywords` 用于 PostgreSQL 关键词匹配。

## 4. 向量召回

向量召回继续使用：

```sql
ORDER BY chunk.embedding <=> %s::vector
LIMIT %s
```

初始召回数建议大于最终上下文数，例如向量 Top30。

## 5. 关键词召回

关键词检索检查正文和文件名：

```sql
chunk.content ILIKE %s
OR document.file_name ILIKE %s
```

当前简单权重：

```text
正文命中关键词：+1
文件名命中关键词：+2
```

用户关键词必须使用 psycopg 参数绑定。`%`、`_` 和反斜杠在构造 `ILIKE` 模式前需要转义。

SQL 参数顺序必须与占位符出现顺序一致：

```text
SELECT 正文评分参数
-> SELECT 文件名评分参数
-> tenant_id
-> knowledge_base_id
-> WHERE 匹配参数
-> LIMIT
```

错误的顺序会把 `BIGINT tenant_id` 绑定到 `ILIKE`，产生 `like_escape(bigint, unknown)` 异常。

## 6. RRF 融合

RRF 不直接比较向量分数和关键词分数，只使用排名：

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

当前建议：

```text
k = 60
```

同一个 `chunk_id` 同时被两路召回时，合并为一条候选，并同时获得两路排名加分。

## 7. 统一候选数据

`RetrievalCandidate` 保存：

- 分片、文档和知识库 ID。
- 分片正文和文档名称。
- `vectorScore`、`keywordScore`。
- `vectorRank`、`keywordRank`。
- `fusionScore`。
- `retrievalSources`。

融合完成后转换为 LangChain `Document`，继续复用现有 `ContextPacker`。

## 8. 降级策略

```text
向量成功 + 关键词失败 -> 使用向量结果
向量失败 + 关键词成功 -> 使用关键词结果
两路成功              -> RRF 融合
两路都无结果          -> 空上下文
两路都异常            -> 抛出检索异常
关键词为空            -> 跳过关键词检索
```

## 9. 配置

```dotenv
RETRIEVAL_VECTOR_TOP_K=30
RETRIEVAL_KEYWORD_TOP_K=30
RETRIEVAL_FINAL_TOP_K=8
RETRIEVAL_RRF_K=60
RETRIEVAL_ENABLE_KEYWORD=true
```

## 10. 已处理问题

### SQL 缺少表别名

错误写法：

```sql
FROM kb_document_chunk
JOIN kb_document document
  ON document.id = chunk.document_id
```

正确写法：

```sql
FROM kb_document_chunk chunk
```

### `KeywordRetriever.retrieve()` 无法调用

原因是 `retrieve()` 错误缩进到 `__init__()` 内部。它必须和 `__init__()` 保持同级。

### `like_escape(bigint, unknown)`

原因是动态 SQL 的参数绑定顺序错误，不是 `pg_trgm` 或字段类型错误。

## 11. 验收标准

- 向量和关键词两路均能独立返回结果。
- 相同分片只保留一次。
- 同时命中两路的分片获得两项 RRF 加分。
- 引用信息包含两路分数、排名和召回来源。
- 单路异常时能够降级。
- SQL 始终包含租户、知识库和软删除过滤。
- 混合检索结果能够进入 Context Packing 和最终回答。

## 12. 后续步骤

Step 20 在 RRF 候选结果后加入 Cross Encoder Rerank，对问题和候选分片进行更精确的相关性判断。
