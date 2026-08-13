package com.example.rag.ingestion.service;

import com.example.rag.common.context.LoginUser;
import com.example.rag.common.context.RequestContext;
import com.example.rag.ingestion.dto.IngestionTaskCreateCommand;
import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.event.IngestionTaskStartEvent;
import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.pipeline.StepCode;
import com.example.rag.knowledge.entity.KnowledgeDocument;
import com.example.rag.knowledge.mapper.KnowledgeBaseMapper;
import com.example.rag.knowledge.mapper.KnowledgeDocumentMapper;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ServiceException;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * 文档和入库任务事务注册服务。
 *
 * <p>文档、任务和任务步骤在同一个事务中保存；流水线启动事件
 * 由 AFTER_COMMIT 监听器在事务成功提交后处理。</p>
 */
@Service
@RequiredArgsConstructor
public class DocumentIngestionRegistrationService {

    private final KnowledgeDocumentMapper documentMapper;

    private final KnowledgeBaseMapper knowledgeBaseMapper;

    private final IngestionTaskService ingestionTaskService;

    private final ApplicationEventPublisher eventPublisher;
    private final IngestionMetrics ingestionMetrics;

    /**
     * 原子保存文档和入库任务，并发布流水线启动事件。
     */
    @Transactional(rollbackFor = Exception.class)
    public IngestionTask register(
            KnowledgeDocument document,
            IngestionTaskCreateCommand command,
            LoginUser loginUser
    ) {
        // 保存文档元数据。
        documentMapper.insert(document);

        // 文档插入和知识库计数递增处于同一事务，任一失败都会整体回滚。
        int updatedRows = knowledgeBaseMapper.incrementDocumentCount(
                document.getKnowledgeBaseId(),
                document.getTenantId()
        );
        if (updatedRows != 1) {
            throw new ServiceException(
                    BaseErrorCode.DATABASE_ERROR,
                    "更新知识库文档数量失败"
            );
        }

        // 使用已保存文档的 ID 创建入库任务。
        command.setDocumentId(document.getId());
        IngestionTask task =
                ingestionTaskService.createDocumentIngestTask(command);
        // 事务真正提交后再统计任务创建数量。
        recordTaskCreatedAfterCommit(task);
        // 监听器会在当前事务提交成功后异步启动流水线。
        eventPublisher.publishEvent(
                new IngestionTaskStartEvent(
                        task.getId(),
                        loginUser,
                        StepCode.first(),
                        RequestContext.requestId()
                )
        );
        return task;
    }
    /**
     * 在数据库事务提交成功后记录任务创建指标。
     */
    private void recordTaskCreatedAfterCommit(
            IngestionTask task
    ) {
        if (TransactionSynchronizationManager
                .isSynchronizationActive()) {
            TransactionSynchronizationManager
                    .registerSynchronization(
                            new TransactionSynchronization() {
                                @Override
                                public void afterCommit() {
                                    ingestionMetrics.recordTaskCreated(
                                            task.getTaskType()
                                    );
                                }
                            }
                    );
            return;
        }

        // 没有事务时直接记录，作为防御性处理。
        ingestionMetrics.recordTaskCreated(
                task.getTaskType()
        );
    }
}
