package com.example.rag.chat.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * ConversationSummaryProperties
 * 会话压缩配置
 * @author gel
 * @date 2026/8/12
 * @description 
 */
@Data
@Component
@ConfigurationProperties(prefix = "rag.summary")
public class ConversationSummaryProperties {
    private boolean enabled = true;
    private int countThreshold = 15;
    private int tokenThreshold = 2000;
    private int gapCount = 5;
    private int gapTokens = 500;
    private int keepRecent = 10;
}