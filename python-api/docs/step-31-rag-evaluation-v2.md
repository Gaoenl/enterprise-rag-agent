# Step 31：RAG 检索测评 V2

## 本次解决的问题

V1 使用 50 篇正确文档和 450 篇随机负样本。问题与正确文档的字面重合度较高，导致向量、关键词、混合和重排实验都可能得到 100% 的文档级命中率。

V2 完成以下调整：

1. 基础四组实验统一关闭 Query Rewrite。
2. 新增 `HYBRID_REWRITE` 和 `HYBRID_REWRITE_RERANK` 对照实验。
3. 文档级排名按 `document_id` 去重。
4. Case 明细返回语义查询、关键词、真实 Top 8 分块及各阶段分数。
5. 支持可选 `gold_evidence_texts`，有人工证据标注时才计算分块指标。
6. 从完整 CRUD-RAG 语料中选择与问题相似但不是正确文档的 Hard Negative。

## 已生成数据

数据目录：

```text
python-api/evaluation/datasets/crud_v2
```

当前规模：

```text
问题数：50
正确文档：50
负样本文档：950
去重后的 Hard Negative：490
总文档数：1000
```

## 重新生成

在 `python-api` 目录执行：

```powershell
E:\Develop\Anaconda\envs\ai-env\python.exe -B -m scripts.prepare_crud_v2 `
  --crud-root E:\AI\RAGELV\CRUD_RAG-main
```

输出目录必须为空，防止误覆盖已经用于测评的数据。

## 使用步骤

1. 新建一个专门用于 `CRUD_RAG_V2` 的知识库。
2. 上传 `evaluation/datasets/crud_v2/documents` 下全部 1000 个 TXT 文件。
3. 等待所有文件完成解析、切分和向量化。
4. 打开前端“RAG 测评”。
5. 选择新知识库和 `CRUD-RAG V2（Hard Negative）`。
6. 首先运行四组无 Rewrite 实验，比较纯检索算法。
7. 再运行 Rewrite 对照实验，判断问题改写带来的增益和耗时。

V2 数据集与知识库必须配套。仅在前端切换为 V2、但仍使用原 V1 知识库，不会产生有效的 Hard Negative 测评结果。
