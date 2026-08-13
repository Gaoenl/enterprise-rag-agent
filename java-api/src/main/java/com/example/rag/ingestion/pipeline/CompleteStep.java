package com.example.rag.ingestion.pipeline;

import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.service.IngestionTaskService;
import com.example.rag.knowledge.enums.DocumentProcessStatus;
import com.example.rag.knowledge.service.KnowledgeDocumentService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * 收尾步骤。
 *
 * <p>流水线的最后一步：将文档解析状态标记为 READY，任务标记为 SUCCESS。
 * 在独立事务中执行，提交后不可回滚。</p>
 */
@Slf4j
@Component
public class CompleteStep extends PipelineStep {

    public CompleteStep(IngestionTaskService taskService,
                        KnowledgeDocumentService documentService,
                        IngestionMetrics ingestionMetrics) {
        super(taskService, documentService,ingestionMetrics);
    }

    @Override
    public StepCode code() {
        return StepCode.COMPLETE;
    }

    @Override
    protected void doExecute(Long taskId) {
        IngestionTask task = requireTask(taskId);

        documentService.markParseStatus(task.getDocumentId(),
                DocumentProcessStatus.READY.getCode());
        taskService.markTaskSuccess(taskId);

        log.info("入库流程完成, taskId={}, docId={}", taskId, task.getDocumentId());
    }
}
