# 测评与可观测性

[返回目录](README.md)

## 检索调试

Java `/api/retrieval/debug` 与 `/api/retrieval/config` 面向管理角色，注入用户/租户后调用 Python。调试执行改写、向量/关键词、融合、重排、上下文打包，不生成最终自然语言回答，适合把召回问题与生成问题分开定位。

响应包含各阶段候选、来源、排名、分数、耗时、降级信息与打包后的上下文。比较时固定知识库、数据版本、模型、topK 和开关；候选内容、文档 ID 与引用必须属于同一租户。

## 异步检索测评

`POST /api/evaluations/retrieval` 创建作业，`GET /{runId}` 轮询，`GET /{runId}/result` 取结果。Python 查询要求 tenantId/userId 并与作业所有者核对；Java 从认证上下文传入。作业状态 PENDING → RUNNING → SUCCESS/FAILED。

EvaluationService 用一个 max_workers=1 的线程池和 `_jobs` 字典管理作业。不是持久化任务系统：重启丢失作业，多个 worker 也不共享状态。部署多 worker 前应先解决状态共享或路由一致性，不能任意扩容后继续保证 runId 可查询。

## 九组实验

| 实验 | 改写 | 重排 | 多查询 | 读取结果 |
| --- | --- | --- | --- | --- |
| VECTOR | 否 | 否 | 否 | vector_results |
| KEYWORD | 否 | 否 | 否 | keyword_results |
| HYBRID | 否 | 否 | 否 | fusion_results |
| HYBRID_RERANK | 否 | 是 | 否 | rerank_results |
| HYBRID_REWRITE | 是 | 否 | 否 | fusion_results |
| HYBRID_REWRITE_RERANK | 是 | 是 | 否 | rerank_results |
| HYBRID_MULTI_QUERY | 否 | 否 | 是 | fusion_results |
| HYBRID_MULTI_QUERY_REWRITE | 是 | 否 | 是 | fusion_results |
| HYBRID_MULTI_QUERY_REWRITE_RERANK | 是 | 是 | 是 | rerank_results |

基础四组显式关闭改写，避免改写掩盖算法差异。配置以 EXPERIMENT_CONFIG 为准。

## 指标口径

- Hit@1/3/5/8：首 K 个结果中是否命中目标文档，在全部 case 上取比例。
- MRR：首个正确结果排名倒数，未命中为 0，在全部 case 上平均。
- chunkHitAt5：只在 evidenceEvaluated 的证据样本上计算；没有证据样本时是 null，不是 0。
- failedCount/degradedCount：分别统计失败与降级，不应只看成功样本延迟。
- averageLatencyMillis：延迟平均；P95 取排序后 ceil(N×0.95)-1 的位置。

测评当前聚焦检索效果，不能直接等同于回答正确率、忠实度、幻觉率或完整 RAG 质量分。导出结果应附数据集、实验参数、模型、语料入库状态与失败数量。

## 数据集与脚本

数据在 `apps/evaluation/datasets`，支持 CRUD_RAG_V1 和 CRUD_RAG_V2。每组有 cases.jsonl、corpus-manifest.jsonl、summary.json 和 documents。映射通过 document_key → file_name 建立，语料必须先进入对应知识库，文件名变化会影响命中判断。

scripts/prepare_crud_v1.py、prepare_crud_v2.py 与 crud_dataset_preparer.py 用于准备数据；generate_test_kb.py 生成测试知识；evaluate_intent.py 使用 intent_v1.json 评估意图。运行前先查看脚本 `--help` 和配置，确认输入输出路径及是否调用远程 API，勿直接对生产库批量导入。

## Trace

Python TraceRecorder 记录节点输入输出摘要、状态、耗时和 Token；RagEngine 节点包括 QUERY_RESOLVE、QUERY_ROUTE、KNOWLEDGE_BASE_SELECT、RETRIEVAL_QUERY_REWRITE、HYBRID_RETRIEVE、RERANK、CONTEXT_PACK、LLM_GENERATE、ANSWER_POST_PROCESS、TOOL_EXECUTE。短路阶段可记录 SKIPPED。

Java RagTraceService 保存追踪结果，管理端按列表/统计/详情查询。requestId 用于日志，traceId 用于业务追踪，taskId 用于入库，它们不是同一个 ID。Trace 可能包含问题、文档片段和错误，应按租户控制访问。

## 入库指标

IngestionMetrics 注册：rag.ingestion.task.created、rag.ingestion.task.completed、rag.ingestion.task.duration、rag.ingestion.step.completed、rag.ingestion.step.duration、rag.ingestion.embedding.batch.duration。

Actuator 配置暴露 health/info/metrics。当前 POM/部署未形成 Prometheus + Grafana 或 OpenTelemetry 完整链路；不能把 Micrometer 埋点描述为已部署告警平台。新增 tag 避免将每个 taskId/文档名作为指标维度造成高基数。

源码：[测评服务](../../python-api/app/apps/evaluation/evaluation_service.py)、[调试服务](../../python-api/app/apps/evaluation/debug_service.py)、[指标](../../java-api/src/main/java/com/example/rag/ingestion/service/IngestionMetrics.java)。
