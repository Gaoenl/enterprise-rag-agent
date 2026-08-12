package com.example.rag.chat.config;

import com.example.rag.chat.entity.ChatMessage;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * ConversationMemoryCache
 * redis
 * @author gel
 * @date 2026/8/12
 * @description 
 */
@Component
@RequiredArgsConstructor
public class ConversationMemoryCache {
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    @Value("${rag.redis.enabled:false}")
    private boolean enabled;
    private static final long TTL_SECONDS = 86400;

    /** 保存消息到工作记忆（Redis List，最新在前）。 */
    public void pushMessage(Long conversationId, String role, String content) {
        if (!enabled) {
            return;
        }
        String key = "wm:" + conversationId;
        redisTemplate.opsForList().leftPush(key, json(role, content));
        redisTemplate.expire(key, Duration.ofSeconds(TTL_SECONDS));

    }
    /** 保存会话摘要。 */
    public void saveSummary(Long conversationId, String summary) {
        if (!enabled || summary == null) {
            return;
        }
        redisTemplate.opsForValue().set(
                "wm:" + conversationId + ":summary",
                summary,
                Duration.ofSeconds(TTL_SECONDS));
    }

    /** 读取会话摘要，未命中返回 null。 */
    public String getSummary(Long conversationId) {
        if (!enabled) {
            return null;
        }
        return redisTemplate.opsForValue().get(
                "wm:" + conversationId + ":summary"
        );
    }

    /** 读取最近 N 条消息（按时间正序），未命中返回空列表。 */
    public List<ChatMessage> getRecentMessages(Long conversationId, int limit) {
        if (!enabled) {
            return List.of();
        }
        String key = "wm:" + conversationId;
        // Redis List 最新在前，反序还原为时间正序。
        List<String> raws = redisTemplate.opsForList().range(key, 0, limit - 1);
        if (raws == null || raws.isEmpty()) {
            return List.of();
        }
        List<ChatMessage> messages = new ArrayList<>();
        for (int i = raws.size() - 1; i >= 0; i--) {
            try {
                Map<?, ?> node = objectMapper.readValue(raws.get(i), Map.class);
                ChatMessage message = new ChatMessage();
                message.setRole(String.valueOf(node.get("role")));
                message.setContent(String.valueOf(node.get("content")));
                Object ts = node.get("ts");
                if (ts != null) {
                    message.setCreatedAt(Instant.parse(String.valueOf(ts)));
                }
                messages.add(message);
            } catch (Exception exception) {
                // 单条解析失败跳过，不影响其余消息。
            }
        }
        return messages;
    }
    /** 压缩后只保留最近 N 条原文。 */
    public void trimWorkingMemory(Long conversationId, int keepRecent) {
        if (!enabled) {
            return;
        }
        redisTemplate.opsForList().trim("wm:" + conversationId, 0, keepRecent - 1);
    }
    /** 删除会话时清理。 */
    public void delete(Long conversationId) {
        redisTemplate.delete(java.util.List.of(
                "wm:" + conversationId,
                "wm:" + conversationId + ":summary"));
    }
    private String json(String role, String content) {
        try {
            return objectMapper.writeValueAsString(Map.of(
                    "role", role,
                    "content", content,
                    "ts", Instant.now().toString()));
        } catch (Exception e) {
            return role + ":" + content;
        }
    }
}
