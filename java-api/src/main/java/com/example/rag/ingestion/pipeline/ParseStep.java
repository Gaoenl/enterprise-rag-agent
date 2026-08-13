package com.example.rag.ingestion.pipeline;

import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.processor.DocumentIngestionProcessor;
import com.example.rag.ingestion.service.IngestionTaskService;
import com.example.rag.knowledge.enums.DocumentProcessStatus;
import com.example.rag.knowledge.service.KnowledgeDocumentService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * 文档解析步骤。
 *
 * <p>委托 {@link DocumentIngestionProcessor#parseAndSaveChunks(Long)} 执行核心逻辑：
 * 下载 → Tika 解析 → 文本清洗 → 切分 → Chunk 入库。</p>
 *
 * <p>任务状态（RUNNING/FAILED）由父类 {@link PipelineStep#execute(Long)} 统一管理。</p>
 */
@Slf4j
@Component
public class ParseStep extends PipelineStep {

    private final DocumentIngestionProcessor processor;

    public ParseStep(IngestionTaskService taskService,
                     KnowledgeDocumentService documentService,
                     IngestionMetrics ingestionMetrics,
                     DocumentIngestionProcessor processor) {
        super(taskService, documentService,ingestionMetrics);
        this.processor = processor;
    }

    @Override
    public StepCode code() {
        return StepCode.PARSE;
    }

    @Override
    protected void doExecute(Long taskId) {
        IngestionTask task = requireTask(taskId);
        documentService.markParseStatus(task.getDocumentId(),
                DocumentProcessStatus.PROCESSING.getCode());
        // 下载和解析开始。
        taskService.updateProgress(taskId, 10);
        int chunkCount = processor.parseAndSaveChunks(taskId);
        documentService.markParseStatus(task.getDocumentId(),
                DocumentProcessStatus.PARSED.getCode());
        // 解析阶段占总流程的前 30%。
        taskService.updateProgress(taskId, 30);
        log.info("文档解析完成, taskId={}, docId={}, chunks={}", taskId, task.getDocumentId(), chunkCount);
    }
}
