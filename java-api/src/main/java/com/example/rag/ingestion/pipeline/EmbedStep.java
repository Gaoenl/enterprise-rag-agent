package com.example.rag.ingestion.pipeline;

import com.example.rag.embedding.config.EmbeddingClientProperties;
import com.example.rag.embedding.service.ChunkEmbeddingService;
import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.enums.IngestionStepCode;
import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.service.IngestionTaskService;
import com.example.rag.ingestion.service.IngestionTaskStepService;
import com.example.rag.knowledge.entity.KnowledgeDocumentChunk;
import com.example.rag.knowledge.enums.DocumentProcessStatus;
import com.example.rag.knowledge.mapper.KnowledgeDocumentChunkMapper;
import com.example.rag.knowledge.service.KnowledgeDocumentService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import com.example.rag.ingestion.config.PipelineConfig;

import java.time.Duration;
import java.util.List;

/**
 * 向量化步骤。
 *
 * <p>委托 {@link ChunkEmbeddingService#embedBatch(List)} 执行单个批次的向量化。
 * 核心设计：<b>每批一个独立事务</b>——批次 N 失败 → 批次 1..N-1 已提交保留。</p>
 */
@Slf4j
@Component
public class EmbedStep extends PipelineStep {

    private final KnowledgeDocumentChunkMapper chunkMapper;
    private final ChunkEmbeddingService embeddingService;
    private final EmbeddingClientProperties properties;
    private final IngestionTaskStepService taskStepService;

    public EmbedStep(IngestionTaskService taskService,
                     KnowledgeDocumentService documentService,
                     IngestionMetrics ingestionMetrics,
                     KnowledgeDocumentChunkMapper chunkMapper,
                     ChunkEmbeddingService embeddingService,
                     EmbeddingClientProperties properties,
                     IngestionTaskStepService taskStepService) {
        super(taskService, documentService,ingestionMetrics);
        this.chunkMapper = chunkMapper;
        this.embeddingService = embeddingService;
        this.properties = properties;
        this.taskStepService = taskStepService;
    }

    @Override
    public StepCode code() {
        return StepCode.EMBED;
    }

    @Override
    protected void doExecute(Long taskId) {
        // 查询并校验任务。
        IngestionTask task = requireTask(taskId);

        // 将文档状态更新为向量化处理中。
        documentService.markParseStatus(
                task.getDocumentId(),
                DocumentProcessStatus.EMBEDDING.getCode()
        );

        // 执行向量生成步骤。
        executeEmbeddingStep(taskId, task);

        /*
         * pgvector 的 HNSW 索引会在 embedding 字段更新时自动维护，
         * 项目不需要额外执行 CREATE INDEX 或刷新索引。
         */
        executeVectorIndexStep(taskId);
    }

    /**
     * 分批生成并保存 Chunk 向量。
     */
    private void executeEmbeddingStep(
            Long taskId,
            IngestionTask task
    ) {
        long stepStartedNanos = System.nanoTime();
        // 将向量生成步骤设置为运行中。
        taskStepService.markRunning(
                taskId,
                IngestionStepCode.EMBEDDING
        );

        try {
            // 只查询尚未生成向量的 Chunk，支持失败后继续执行。
            List<KnowledgeDocumentChunk> chunks =
                    chunkMapper.selectWithoutEmbeddingByDocumentId(
                            task.getDocumentId()
                    );

            if (chunks == null || chunks.isEmpty()) {
                log.info(
                        "没有待向量化 Chunk, taskId={}, documentId={}",
                        taskId,
                        task.getDocumentId()
                );
                ingestionMetrics.recordStepCompleted(
                        IngestionStepCode.EMBEDDING.getCode(),
                        "SUCCESS",
                        elapsed(stepStartedNanos)
                );

                // 没有待处理数据，说明向量已经全部生成。
                taskStepService.markSuccess(
                        taskId,
                        IngestionStepCode.EMBEDDING
                );
                return;
            }

            // 从任务流水线配置读取向量化参数，fallback 到全局默认值。
            PipelineConfig pipelineConfig =
                    task.getPipelineConfig();
            String effectiveModel = resolveModel(pipelineConfig);
            int effectiveDimension = resolveDimension(pipelineConfig);
            int batchSize = resolveBatchSize(pipelineConfig);

            int totalBatches =
                    (int) Math.ceil(
                            (double) chunks.size() / batchSize
                    );

            for (
                    int batchIndex = 0;
                    batchIndex < totalBatches;
                    batchIndex++
            ) {
                // 计算当前批次在 Chunk 列表中的范围。
                int start = batchIndex * batchSize;
                int end = Math.min(
                        start + batchSize,
                        chunks.size()
                );

                List<KnowledgeDocumentChunk> batch =
                        chunks.subList(start, end);

                // 调用 Python Embedding，并在独立事务中保存向量。
                long batchStartedNanos =
                        System.nanoTime();

                try {
                    // 调用 Python Embedding 并保存当前批次向量。
                    embeddingService.embedBatch(
                            batch, effectiveModel, effectiveDimension);

                    ingestionMetrics.recordEmbeddingBatch(
                            "SUCCESS",
                            batch.size(),
                            elapsed(batchStartedNanos)
                    );
                } catch (RuntimeException exception) {
                    ingestionMetrics.recordEmbeddingBatch(
                            "FAILED",
                            batch.size(),
                            elapsed(batchStartedNanos)
                    );

                    throw exception;
                }

                // 向量化阶段占总任务进度的 30% 到 80%。
                int progress =
                        30
                                + (batchIndex + 1)
                                * 50
                                / totalBatches;

                taskService.updateProgress(
                        taskId,
                        progress
                );
            }

            // 所有批次完成后，将向量生成步骤标记为成功。
            taskStepService.markSuccess(
                    taskId,
                    IngestionStepCode.EMBEDDING
            );

            Duration duration =
                    elapsed(stepStartedNanos);

            ingestionMetrics.recordStepCompleted(
                    IngestionStepCode.EMBEDDING.getCode(),
                    "SUCCESS",
                    duration
            );
            log.info(
                    "向量化完成, taskId={}, chunks={}, batches={}",
                    taskId,
                    chunks.size(),
                    totalBatches
            );
        } catch (RuntimeException exception) {
            // 保存向量生成步骤失败状态。
            markStepFailedSafely(
                    taskId,
                    IngestionStepCode.EMBEDDING,
                    exception
            );
            ingestionMetrics.recordStepCompleted(
                    IngestionStepCode.EMBEDDING.getCode(),
                    "FAILED",
                    elapsed(stepStartedNanos)
            );

            throw exception;
        }
    }

    /**
     * 确认 pgvector 索引维护完成。
     */
    private void executeVectorIndexStep(Long taskId) {
        long startedNanos = System.nanoTime();
        // 标记向量索引步骤开始。
        taskStepService.markRunning(
                taskId,
                IngestionStepCode.INDEX_VECTOR
        );

        try {
            /*
             * PostgreSQL HNSW 索引会随着 UPDATE embedding 自动更新。
             * 此处不需要手动重建索引，只记录流程状态。
             */
            taskService.updateProgress(taskId, 90);

            // 标记向量索引步骤完成。
            taskStepService.markSuccess(
                    taskId,
                    IngestionStepCode.INDEX_VECTOR
            );
            ingestionMetrics.recordStepCompleted(
                    IngestionStepCode.INDEX_VECTOR.getCode(),
                    "SUCCESS",
                    elapsed(startedNanos)
            );
        } catch (RuntimeException exception) {
            // 单独记录索引步骤失败。
            markStepFailedSafely(
                    taskId,
                    IngestionStepCode.INDEX_VECTOR,
                    exception
            );
            ingestionMetrics.recordStepCompleted(
                    IngestionStepCode.INDEX_VECTOR.getCode(),
                    "FAILED",
                    elapsed(startedNanos)
            );

            throw exception;
        }
    }

    /**
     * 尝试保存步骤失败状态，同时保留原始异常。
     */
    private void markStepFailedSafely(
            Long taskId,
            IngestionStepCode stepCode,
            RuntimeException exception
    ) {
        try {
            String message =
                    exception.getMessage() == null
                            ? exception.getClass().getSimpleName()
                            : exception.getMessage();

            taskStepService.markFailed(
                    taskId,
                    stepCode,
                    message
            );
        } catch (Exception statusException) {
            // 不让状态记录异常覆盖真正的业务异常。
            exception.addSuppressed(statusException);

            log.error(
                    "保存入库步骤失败状态异常, taskId={}, stepCode={}",
                    taskId,
                    stepCode.getCode(),
                    statusException
            );
        }
    }

    private Duration elapsed(long startedNanos) {
        long elapsedNanos =
                System.nanoTime() - startedNanos;

        return Duration.ofNanos(
                Math.max(elapsedNanos, 0L)
        );
    }

    /** 解析 embedding 模型名，优先用任务配置，否则用全局默认。 */
    private String resolveModel(
            PipelineConfig config) {
        if (config != null
                && config.getEmbeddingModel() != null
                && !config.getEmbeddingModel().isBlank()) {
            return config.getEmbeddingModel();
        }
        return properties.getModel();
    }

    /** 解析向量维度，优先用任务配置，否则用全局默认。 */
    private int resolveDimension(
            com.example.rag.ingestion.config.PipelineConfig config) {
        if (config != null
                && config.getEmbeddingDimension() != null
                && config.getEmbeddingDimension() > 0) {
            return config.getEmbeddingDimension();
        }
        return properties.getDimension();
    }

    /** 解析批处理大小，优先用任务配置，否则用全局默认。 */
    private int resolveBatchSize(
            com.example.rag.ingestion.config.PipelineConfig config) {
        int batchSize = config != null
                ? config.getEffectiveEmbeddingBatchSize(properties.getBatchSize())
                : properties.getBatchSize();
        return Math.max(1, batchSize);
    }

}
