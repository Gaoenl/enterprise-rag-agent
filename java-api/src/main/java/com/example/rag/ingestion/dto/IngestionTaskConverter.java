package com.example.rag.ingestion.dto;

import com.example.rag.common.enums.IngestionTaskStatus;
import com.example.rag.ingestion.dto.IngestionTaskDetailResponse;
import com.example.rag.ingestion.dto.IngestionTaskStepResponse;
import com.example.rag.ingestion.entity.IngestionTask;
import com.example.rag.ingestion.entity.IngestionTaskStep;
import com.example.rag.knowledge.entity.KnowledgeBase;
import com.example.rag.knowledge.entity.KnowledgeDocument;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

/**
 * 入库任务实体与接口响应转换器。
 */
@Component
public class IngestionTaskConverter {

    /**
     * 将任务步骤实体转换为响应对象。
     */
    public IngestionTaskStepResponse toStepResponse(
            IngestionTaskStep step,
            Instant now
    ) {
        if (step == null) {
            return null;
        }

        return IngestionTaskStepResponse.builder()
                .id(step.getId())
                .taskId(step.getTaskId())
                .stepCode(step.getStepCode())
                .stepName(step.getStepName())
                .status(step.getStatus())
                .errorMessage(step.getErrorMessage())
                .startedAt(step.getStartedAt())
                .finishedAt(step.getFinishedAt())
                .durationMillis(calculateDuration(
                        step.getStartedAt(),
                        step.getFinishedAt(),
                        now
                ))
                .build();
    }

    /**
     * 将任务及其关联数据转换为详情响应。
     */
    public IngestionTaskDetailResponse toDetailResponse(
            IngestionTask task,
            KnowledgeBase knowledgeBase,
            KnowledgeDocument document,
            List<IngestionTaskStep> steps
    ) {
        Instant now = Instant.now();

        // 将步骤实体列表转换为接口响应列表。
        List<IngestionTaskStepResponse> stepResponses =
                toStepResponses(steps);
        // 查找当前最值得展示的任务步骤。
        IngestionTaskStep currentStep =
                findCurrentStep(steps);

        return IngestionTaskDetailResponse.builder()
                .id(task.getId())
                .tenantId(task.getTenantId())
                .taskType(task.getTaskType())
                .status(task.getStatus())
                .progress(task.getProgress())
                .errorMessage(task.getErrorMessage())
                .knowledgeBaseId(task.getKnowledgeBaseId())
                .knowledgeBaseName(
                        knowledgeBase == null
                                ? null
                                : knowledgeBase.getName()
                ).knowledgeBaseDeleted(
                        knowledgeBase == null
                                ? null
                                : knowledgeBase.getDeleted()
                )
                .documentId(task.getDocumentId())
                .documentName(
                        document == null
                                ? null
                                : document.getFileName()
                )
                .fileType(
                        document == null
                                ? null
                                : document.getFileType()
                )
                .fileSize(
                        document == null
                                ? null
                                : document.getFileSize()
                )
                .documentStatus(
                        document == null
                                ? null
                                : document.getParseStatus()
                )
                .documentDeleted(
                document == null
                        ? null
                        : document.getDeleted()
        )
                .currentStepCode(
                        currentStep == null
                                ? null
                                : currentStep.getStepCode()
                )
                .currentStepName(
                        currentStep == null
                                ? null
                                : currentStep.getStepName()
                )
                .canRetry(
                        IngestionTaskStatus.FAILED
                                .getCode()
                                .equals(task.getStatus())
                )
                .durationMillis(calculateDuration(
                        task.getStartedAt(),
                        task.getFinishedAt(),
                        now
                ))
                .createdBy(task.getCreatedBy())
                .startedAt(task.getStartedAt())
                .finishedAt(task.getFinishedAt())
                .createdAt(task.getCreatedAt())
                .updatedAt(task.getUpdatedAt())
                .steps(stepResponses)
                .build();
    }
    /**
     * 将任务步骤实体列表转换为响应列表。
     */
    public List<IngestionTaskStepResponse> toStepResponses(
            List<IngestionTaskStep> steps
    ) {
        if (steps == null || steps.isEmpty()) {
            return List.of();
        }

        // 同一次转换统一使用同一个当前时间，避免耗时出现细微差异。
        Instant now = Instant.now();

        return steps.stream()
                .map(step ->
                        toStepResponse(step, now)
                )
                .toList();
    }

    /**
     * 查找任务当前需要展示的步骤。
     *
     * <p>优先级：RUNNING、FAILED、PENDING、最后一个步骤。</p>
     */
    private IngestionTaskStep findCurrentStep(
            List<IngestionTaskStep> steps
    ) {
        if (steps == null || steps.isEmpty()) {
            return null;
        }

        IngestionTaskStep matched =
                findByStatus(steps, "RUNNING");

        if (matched != null) {
            return matched;
        }

        matched = findByStatus(steps, "FAILED");

        if (matched != null) {
            return matched;
        }

        matched = findByStatus(steps, "PENDING");

        if (matched != null) {
            return matched;
        }

        // 全部成功时返回最后一个步骤。
        return steps.get(steps.size() - 1);
    }

    /**
     * 根据状态查找第一个步骤。
     */
    private IngestionTaskStep findByStatus(
            List<IngestionTaskStep> steps,
            String status
    ) {
        return steps.stream()
                .filter(step ->
                        status.equals(step.getStatus())
                )
                .findFirst()
                .orElse(null);
    }

    /**
     * 计算任务或步骤耗时。
     */
    private Long calculateDuration(
            Instant startedAt,
            Instant finishedAt,
            Instant now
    ) {
        if (startedAt == null) {
            return null;
        }

        Instant actualFinishedAt =
                finishedAt == null
                        ? now
                        : finishedAt;

        long duration =
                Duration.between(
                        startedAt,
                        actualFinishedAt
                ).toMillis();

        // 防止服务器时间回拨产生负数。
        return Math.max(duration, 0L);
    }
}