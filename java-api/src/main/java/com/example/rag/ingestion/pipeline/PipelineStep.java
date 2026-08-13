package com.example.rag.ingestion.pipeline;

import com.example.rag.common.enums.IngestionTaskStatus;
import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.service.IngestionTaskService;
import com.example.rag.knowledge.enums.DocumentProcessStatus;
import com.example.rag.knowledge.service.KnowledgeDocumentService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;

/**
 * 流水线步骤抽象基类。
 *
 * <p>每个步骤在自己的 {@link Propagation#REQUIRES_NEW} 事务中执行：
 * <ol>
 *   <li>更新步骤状态为 RUNNING</li>
 *   <li>执行具体业务逻辑</li>
 *   <li>更新步骤状态为 SUCCESS</li>
 * </ol>
 * 失败时独立提交 FAILED 状态，不影响其他步骤的事务。</p>
 */
@Slf4j
public abstract class PipelineStep {

    protected final IngestionTaskService taskService;
    protected final KnowledgeDocumentService documentService;
    protected final IngestionMetrics ingestionMetrics;

    protected PipelineStep(
            IngestionTaskService taskService,
            KnowledgeDocumentService documentService,
            IngestionMetrics ingestionMetrics
    ) {
        this.taskService = taskService;
        this.documentService = documentService;
        this.ingestionMetrics = ingestionMetrics;
    }

    /** 本步骤编码 */
    public abstract StepCode code();

    /**
     * 执行当前流水线阶段。
     */
    public void execute(Long taskId) {
        log.info(
                "流水线阶段开始, step={}, taskId={}",
                code(),
                taskId
        );

        try {
            /*
             * 具体任务步骤状态由 DocumentIngestionProcessor
             * 和 EmbedStep 在真实业务边界上更新。
             */
            doExecute(taskId);
            if (code() == StepCode.COMPLETE) {
                IngestionTask completedTask =
                        taskService.getTask(taskId);

                ingestionMetrics.recordTaskCompleted(
                        "SUCCESS",
                        calculateTaskDuration(completedTask)
                );
            }

            log.info(
                    "流水线阶段完成, step={}, taskId={}",
                    code(),
                    taskId
            );
        } catch (Exception exception) {
            log.error(
                    "流水线阶段失败, step={}, taskId={}",
                    code(),
                    taskId,
                    exception
            );

            // 标记整个入库任务失败。
            taskService.markTaskFailed(
                    taskId,
                    safeMessage(exception)
            );
            try {
                // 查询已经写入 finishedAt 的失败任务。
                IngestionTask failedTask =
                        taskService.getTask(taskId);

                ingestionMetrics.recordTaskCompleted(
                        "FAILED",
                        calculateTaskDuration(failedTask)
                );
            } catch (Exception metricsException) {
                /*
                 * 指标记录失败不能覆盖真正的业务异常。
                 */
                exception.addSuppressed(metricsException);

                log.warn(
                        "记录入库任务失败指标异常, taskId={}",
                        taskId,
                        metricsException
                );
            }

            try {
                // 将文档状态同步更新为失败。
                IngestionTask task =
                        taskService.getTask(taskId);

                documentService.markParseStatus(
                        task.getDocumentId(),
                        DocumentProcessStatus.FAILED.getCode()
                );
            } catch (Exception statusException) {
                exception.addSuppressed(statusException);

                log.warn(
                        "更新文档失败状态异常, taskId={}",
                        taskId,
                        statusException
                );
            }

            throw new StepFailedException(
                    code(),
                    taskId,
                    exception
            );
        }
    }
    /**
     * 子类实现具体业务逻辑。
     */
    protected abstract void doExecute(Long taskId) throws Exception;

    /**
     * 计算任务从开始到结束的执行时间。
     */
    private Duration calculateTaskDuration(
            IngestionTask task
    ) {
        if (task.getStartedAt() == null) {
            return Duration.ZERO;
        }

        Instant finishedAt =
                task.getFinishedAt() == null
                        ? Instant.now()
                        : task.getFinishedAt();

        Duration duration =
                Duration.between(
                        task.getStartedAt(),
                        finishedAt
                );

        return duration.isNegative()
                ? Duration.ZERO
                : duration;
    }
    /**
     * 查询并校验任务存在。
     */
    protected IngestionTask requireTask(Long taskId) {
        return taskService.getTask(taskId);
    }

    private String safeMessage(Throwable ex) {
        return ex.getMessage() != null ? ex.getMessage() : ex.getClass().getSimpleName();
    }

    /**
     * StepCode → ingestion_task_step.stepName 的映射。
     * COMPLETE 不映射（它没有独立的 step 记录）。
     */

    /**
     * 步骤执行失败异常。全局异常处理器返回 500。
     */
    public static class StepFailedException extends RuntimeException {
        private final StepCode stepCode;
        private final Long taskId;

        public StepFailedException(StepCode stepCode, Long taskId, Throwable cause) {
            super("步骤执行失败: " + stepCode + ", taskId=" + taskId, cause);
            this.stepCode = stepCode;
            this.taskId = taskId;
        }

        public StepCode getStepCode() { return stepCode; }
        public Long getTaskId() { return taskId; }
    }
}
