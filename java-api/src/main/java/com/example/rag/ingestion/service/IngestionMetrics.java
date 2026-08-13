package com.example.rag.ingestion.service;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * IngestionMetrics
 * 文档入库业务指标记录器。
 * @author gel
 * @date 2026/8/4
 * @description 
 */
@Component
@RequiredArgsConstructor
public class IngestionMetrics {
    private final MeterRegistry meterRegistry;
    /**
     * 记录新建任务数量。
     */
    public void recordTaskCreated(String taskType){
        Counter.builder("rag.ingestion.task.created")
                .description("创建的文档入库任务数量")
                .tag("taskType", safeTag(taskType))
                .register(meterRegistry)
                .increment();
    }

    /**
     * 记录任务最终状态和总耗时。
     */
    public void recordTaskCompleted(
            String status,
            Duration duration
    ){

        Counter.builder("rag.ingestion.task.completed")
                .description("已结束的文档入库任务数量")
                .tag("status", safeTag(status))
                .register(meterRegistry)
                .increment();
        Timer.builder("rag.ingestion.task.duration")
                .description("文档入库任务总耗时")
                .tag("status", safeTag(status))
                .register(meterRegistry)
                .record(nonNegative(duration));
    }
    /**
     * 记录任务步骤状态和耗时。
     */
    public void recordStepCompleted(
            String stepCode,
            String status,
            Duration duration
    ) {
        Counter.builder("rag.ingestion.step.completed")
                .description("文档入库步骤完成数量")
                .tag("stepCode", safeTag(stepCode))
                .tag("status", safeTag(status))
                .register(meterRegistry)
                .increment();

        Timer.builder("rag.ingestion.step.duration")
                .description("文档入库步骤耗时")
                .tag("stepCode", safeTag(stepCode))
                .tag("status", safeTag(status))
                .register(meterRegistry)
                .record(nonNegative(duration));
    }
    /**
     * 记录单个 Embedding 批次耗时。
     */
    public void recordEmbeddingBatch(
            String status,
            int batchSize,
            Duration duration
    ) {
        Timer.builder("rag.ingestion.embedding.batch.duration")
                .description("Embedding 单批次调用耗时")
                .tag("status", safeTag(status))
                .register(meterRegistry)
                .record(nonNegative(duration));

        meterRegistry.summary(
                "rag.ingestion.embedding.batch.size",
                "status",
                safeTag(status)
        ).record(Math.max(batchSize, 0));
    }

    /**
     * 防止指标标签出现 null 或空字符串。
     */
    private String safeTag(String value) {
        return value == null || value.isBlank()
                ? "UNKNOWN"
                : value;
    }
    /**
     * 防止时间回拨或计算错误产生负耗时。
     */
    private Duration nonNegative(Duration duration) {
        if (duration == null || duration.isNegative()) {
            return Duration.ZERO;
        }

        return duration;
    }

}