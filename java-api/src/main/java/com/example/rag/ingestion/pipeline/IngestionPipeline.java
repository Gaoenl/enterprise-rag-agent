package com.example.rag.ingestion.pipeline;

import com.example.rag.ingestion.service.IngestionMetrics;
import com.example.rag.ingestion.pipeline.*;
import com.example.rag.ingestion.service.IngestionTaskService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
public class IngestionPipeline {

    private final Map<StepCode, PipelineStep> stepRegistry;
    private final IngestionTaskService taskService;

    public IngestionPipeline(
            IngestionTaskService taskService,
            Map<String, PipelineStep> stepBeans
    ) {
        this.taskService = taskService;
        this.stepRegistry = Map.of(
                StepCode.PARSE,
                requireBean(stepBeans, ParseStep.class),
                StepCode.EMBED,
                requireBean(stepBeans, EmbedStep.class),
                StepCode.COMPLETE,
                requireBean(stepBeans, CompleteStep.class)
        );

    }

    /**
     * 从指定步骤开始顺序执行流水线。
     */
    public void execute(
            Long taskId,
            StepCode startStep
    ) {
        StepCode actualStart =
                startStep == null
                        ? StepCode.first()
                        : startStep;

        log.info(
                "入库流水线开始, taskId={}, startStep={}",
                taskId,
                actualStart
        );

        // 整条流水线只在启动时设置一次任务 RUNNING。
        taskService.markTaskRunning(taskId);
        for (StepCode stepCode : StepCode.values()) {
            // 跳过恢复位置之前的步骤。
            if (stepCode.ordinal() < actualStart.ordinal()) {
                continue;
            }

            PipelineStep executor =
                    stepRegistry.get(stepCode);

            if (executor == null) {
                throw new IllegalStateException(
                        "未找到流水线执行器：" + stepCode
                );
            }

            try {
                executor.execute(taskId);
            } catch (PipelineStep.StepFailedException exception) {
                log.error(
                        "入库流水线终止, taskId={}, step={}",
                        taskId,
                        stepCode,
                        exception
                );
                return;
            }
        }

        log.info(
                "入库流水线完成, taskId={}",
                taskId
        );
    }

    private static PipelineStep requireBean(
            Map<String, PipelineStep> beans,
            Class<? extends PipelineStep> type
    ) {
        return beans.values()
                .stream()
                .filter(type::isInstance)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException(
                                "未找到 PipelineStep Bean："
                                        + type.getSimpleName()
                        )
                );
    }
}