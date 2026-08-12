package com.example.rag.chat.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

/**
 * SummarizationExecutorConfig
 * 
 * @author gel
 * @date 2026/8/12
 * @description 
 */
@Configuration
public class SummarizationExecutorConfig {
    @Bean("summarizationExecutor")
    public Executor summarizationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("summary-");
        executor.initialize();
        return executor;
    }
}