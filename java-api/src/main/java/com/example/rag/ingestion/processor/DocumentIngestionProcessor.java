package com.example.rag.ingestion.processor;

import com.example.rag.common.error.DocumentIngestionException;
import com.example.rag.common.id.IdGenerator;
import com.example.rag.common.storage.ObjectStorageService;
import com.example.rag.ingestion.chunk.TextChunk;
import com.example.rag.ingestion.chunk.TextChunker;
import com.example.rag.ingestion.chunk.TextChunkerFactory;
import com.example.rag.ingestion.chunk.TextNormalizer;
import com.example.rag.ingestion.config.PipelineConfig;
import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.enums.IngestionStepCode;
import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.parser.DocumentParser;
import com.example.rag.ingestion.parser.ParsedDocument;
import com.example.rag.ingestion.service.ChunkPersistenceService;
import com.example.rag.ingestion.service.IngestionTaskService;
import com.example.rag.ingestion.service.IngestionTaskStepService;
import com.example.rag.knowledge.entity.KnowledgeDocument;
import com.example.rag.knowledge.enums.DocumentProcessStatus;
import com.example.rag.knowledge.entity.KnowledgeDocumentChunk;
import com.example.rag.knowledge.mapper.KnowledgeDocumentChunkMapper;
import com.example.rag.knowledge.service.KnowledgeDocumentService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.io.InputStream;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

/**
 * 文档入库处理器。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class DocumentIngestionProcessor {

    /**
     * @deprecated 改为从 ingestion_task.pipeline_config 读取，常量仅用作 fallback。
     */
    @Deprecated
    private static final int DEFAULT_CHUNK_SIZE = 800;

    /** @deprecated */
    @Deprecated
    private static final int DEFAULT_OVERLAP = 100;

    /** @deprecated */
    @Deprecated
    private static final String DEFAULT_CHUNKER_TYPE = "recursive";

    private final IngestionTaskService ingestionTaskService;

    private final KnowledgeDocumentService documentService;
    private final ObjectStorageService objectStorageService;
    private final DocumentParser documentParser;
    private final TextNormalizer textNormalizer;
    private final TextChunkerFactory textChunkerFactory;
    private final IdGenerator idGenerator;
    private final ObjectMapper objectMapper;
    private final ChunkPersistenceService chunkPersistenceService;
    private final IngestionTaskStepService taskStepService;
    private final IngestionMetrics ingestionMetrics;

    /**
     * 执行文档解析、切分和 Chunk 入库（含任务状态管理）。
     *
     * @deprecated 新代码请使用 {@link #parseAndSaveChunks(Long)} + 流水线编排。
     */
//    @Transactional(rollbackFor = Exception.class)
//    @Deprecated
//    public void process(Long taskId) {
//        try {
//            IngestionTask task = ingestionTaskService.getTask(taskId);
//            ingestionTaskService.markTaskRunning(taskId);
//
//            parseAndSaveChunks(taskId);
//
//            documentService.markParseStatus(task.getDocumentId(),
//                    DocumentProcessStatus.PARSED.getCode());
//            ingestionTaskService.markTaskSuccess(taskId);
//        } catch (Exception ex) {
//            log.error("文档入库处理失败, taskId={}", taskId, ex);
//            ingestionTaskService.markTaskFailed(taskId, safeErrorMessage(ex));
//            throw new DocumentIngestionException(taskId, ex);
//        }
//    }

    /**
     * 执行文档解析、切分和 Chunk 入库（不含任务状态管理）。
     *
     * <p>供流水线 {@link com.example.rag.ingestion.pipeline.ParseStep} 调用。
     * 任务状态由调用方（PipelineStep 基类）统一管理。</p>
     *
     * @param taskId 入库任务 ID
     * @return 生成的 Chunk 数量
     */
    public int parseAndSaveChunks(Long taskId) {
        IngestionTask task = ingestionTaskService.getTask(taskId);
        KnowledgeDocument document = documentService.getDocument(task.getDocumentId());

        // 第一阶段：从对象存储下载文件并解析文本。
        ParsedDocument parsedDocument = executeTrackedStep(
                taskId,
                IngestionStepCode.PARSE_DOCUMENT,
                () -> parseDocument(document)
        );
        // 第二阶段：清洗文本并执行分块（使用任务配置）。
        PipelineConfig pipelineConfig =
                task.getPipelineConfig() != null
                        ? task.getPipelineConfig()
                        : PipelineConfig.defaults();
        List<TextChunk> chunks = executeTrackedStep(
                taskId,
                IngestionStepCode.SPLIT_CHUNK,
                () -> splitDocument(parsedDocument, pipelineConfig)
        );

        // 获取实际使用的分块器，用于保存分块元数据。
        TextChunker chunker =
                textChunkerFactory.getChunker(pipelineConfig.getChunkType());
        // 第三阶段：将分块保存到 PostgreSQL。
        executeTrackedStep(
                taskId,
                IngestionStepCode.SAVE_CHUNK,
                () -> {
                    saveChunks(
                            task,
                            document,
                            chunks,
                            chunker.type()
                    );
                    return null;
                }
        );
        return chunks.size();

    }
    /**
     * 清洗解析文本并执行切分。
     */
    private List<TextChunk> splitDocument(
            ParsedDocument parsedDocument,
            com.example.rag.ingestion.config.PipelineConfig config
    ) {
        // 对解析文本进行换行、空白字符等标准化。
        String normalizedText =
                textNormalizer.normalize(parsedDocument.getText());

        // 从任务流水线配置读取切分参数，缺失字段 fallback 到默认值。
        String chunkerType = config.getChunkType() != null
                ? config.getChunkType()
                : DEFAULT_CHUNKER_TYPE;
        int chunkSize = config.getChunkSize() != null && config.getChunkSize() > 0
                ? config.getChunkSize()
                : DEFAULT_CHUNK_SIZE;
        int overlap = config.getChunkOverlap() != null && config.getChunkOverlap() >= 0
                ? config.getChunkOverlap()
                : DEFAULT_OVERLAP;

        // 根据配置取得对应的分块器。
        TextChunker chunker =
                textChunkerFactory.getChunker(chunkerType);

        // 执行文本切分。
        return chunker.chunk(
                normalizedText,
                chunkSize,
                overlap
        );
    }

    /**
     * 执行一个可跟踪的入库步骤。
     *
     * <p>步骤状态单独使用 REQUIRES_NEW 事务保存，因此即使业务失败，
     * RUNNING 或 FAILED 状态也不会跟随业务事务一起回滚。</p>
     */
    private <T> T executeTrackedStep(
            Long taskId,
            IngestionStepCode stepCode,
            Supplier<T> action
    ) {
        // nanoTime 只用于计算时间差，不受系统时间校准影响。
        long startedNanos = System.nanoTime();

        try {
            // 业务开始前将步骤设置为 RUNNING。
            taskStepService.markRunning(taskId, stepCode);
            // 执行当前步骤的真实业务逻辑。
            T result = action.get();

            // 业务执行完成后将步骤设置为 SUCCESS。
            taskStepService.markSuccess(taskId, stepCode);
            Duration duration =
                    elapsed(startedNanos);
            // 记录步骤成功指标。
            ingestionMetrics.recordStepCompleted(
                    stepCode.getCode(),
                    "SUCCESS",
                    duration
            );

            return result;
        } catch (RuntimeException exception) {
            try {
                // 单独保存当前步骤的失败原因。
                taskStepService.markFailed(
                        taskId,
                        stepCode,
                        safeErrorMessage(exception)
                );
                Duration duration =
                        elapsed(startedNanos);

                // 记录步骤失败指标。
                ingestionMetrics.recordStepCompleted(
                        stepCode.getCode(),
                        "FAILED",
                        duration
                );
            } catch (Exception statusException) {
                /*
                 * 状态保存失败不能覆盖最初的业务异常，
                 * 将状态异常作为 suppressed exception 附加保存。
                 */
                exception.addSuppressed(statusException);

                log.error(
                        "保存入库步骤失败状态异常, taskId={}, stepCode={}",
                        taskId,
                        stepCode.getCode(),
                        statusException
                );
            }

            // 继续抛出原始异常，由 PipelineStep 负责标记整个任务失败。
            throw exception;
        }
    }
    private ParsedDocument parseDocument(KnowledgeDocument document) {
        try (InputStream inputStream = objectStorageService.download(document.getFileUri())) {
            // 调用文档解析器提取纯文本。
            return documentParser.parse(inputStream, document.getFileName());
        } catch (Exception ex) {
            throw new RuntimeException("读取或解析文档失败", ex);
        }
    }
    /**
     * 计算从指定 nanoTime 到当前时间的耗时。
     */
    private Duration elapsed(long startedNanos) {
        long elapsedNanos =
                System.nanoTime() - startedNanos;

        return Duration.ofNanos(
                Math.max(elapsedNanos, 0L)
        );
    }
    private void saveChunks(IngestionTask task,
                            KnowledgeDocument document,
                            List<TextChunk> chunks,
                            String chunkerType) {


        Instant now = Instant.now();

        List<KnowledgeDocumentChunk> entities = new ArrayList<>(chunks.size());
        for (TextChunk chunk : chunks) {
            KnowledgeDocumentChunk entity = new KnowledgeDocumentChunk();
            entity.setId(idGenerator.nextId());
            entity.setTenantId(task.getTenantId());
            entity.setKnowledgeBaseId(task.getKnowledgeBaseId());
            entity.setDocumentId(document.getId());
            entity.setChunkIndex(chunk.getChunkIndex());
            entity.setContent(chunk.getContent());
            entity.setTokenCount(estimateTokenCount(chunk.getContent()));
            entity.setEmbeddingModel(null);
            entity.setMetadata(buildMetadata(document.getFileName(), chunkerType, chunk));
            entity.setCreatedAt(now);
            entity.setUpdatedAt(now);
            entity.setDeleted(false);
            entities.add(entity);
        }
        chunkPersistenceService.replaceDocumentChunks(
                document.getId(),
                entities
        );


    }


    private String buildMetadata(String fileName, String chunkerType, TextChunk chunk) {
        Map<String,Object> meta=new LinkedHashMap<>();
        meta.put("sourceFileName", fileName);
        meta.put("chunkerType", chunkerType);
        meta.put("startOffset", chunk.getStartOffset());
        meta.put("endOffset", chunk.getEndOffset());
        try {
            return objectMapper.writeValueAsString(meta);
        } catch (JsonProcessingException e) {
            return "{}";
        }

    }
    private String safeErrorMessage(Throwable ex) {
        return ex.getMessage() != null ? ex.getMessage() : ex.getClass().getSimpleName();
    }



    private int estimateTokenCount(String content) {
        if (content == null || content.isBlank()) {
            return 0;
        }

        return Math.max(1, content.length() / 2);
    }

    private String escapeJson(String value) {
        if (value == null) {
            return "";
        }

        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}