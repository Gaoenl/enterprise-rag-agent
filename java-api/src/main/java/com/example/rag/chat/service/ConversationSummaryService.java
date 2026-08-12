package com.example.rag.chat.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.rag.chat.client.PythonConversationClient;
import com.example.rag.chat.config.ConversationMemoryCache;
import com.example.rag.chat.config.ConversationSummaryProperties;
import com.example.rag.chat.entity.ChatConversation;
import com.example.rag.chat.entity.ChatMessage;
import com.example.rag.chat.mapper.ChatConversationMapper;
import com.example.rag.chat.mapper.ChatMessageMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.List;
import java.util.concurrent.Executor;

/**
 * ConversationSummaryService
 * 
 * @author gel
 * @date 2026/8/12
 * @description 
 */
@Service
@Slf4j
public class ConversationSummaryService {
    private final ConversationSummaryProperties properties;
    private final ChatConversationMapper conversationMapper;
    private final ChatMessageMapper messageMapper;
    private final PythonConversationClient summaryClient;
    private final ConversationMemoryCache memoryCache;
    private final Executor executor;

    public ConversationSummaryService(
            ConversationSummaryProperties properties,
            ChatConversationMapper conversationMapper,
            ChatMessageMapper messageMapper,
            PythonConversationClient summaryClient,
            ConversationMemoryCache memoryCache,
            @Qualifier("summarizationExecutor") Executor executor
    ) {
        this.properties = properties;
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
        this.summaryClient = summaryClient;
        this.memoryCache = memoryCache;
        this.executor = executor;
    }

    /** 保存消息后调用；事务提交后再触发异步压缩。 */
    public void triggerAfterCommit(Long conversationId){
        if (!properties.isEnabled()) {
            return;
        }
        if(TransactionSynchronizationManager.isSynchronizationActive()){
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization(){
                        @Override
                        public void afterCommit(){
                            executor.execute(()->compressSafely(conversationId));
                        }

                    }
            );
        }else {
            executor.execute(()->compressSafely(conversationId));
        }
    }
    private void compressSafely(Long conversationId) {
        try {
            compress(conversationId);
        } catch (Exception exception) {
            log.error("会话摘要压缩失败, conversationId={}", conversationId, exception);
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void compress(Long conversationId) throws Exception {
        ChatConversation conversation = conversationMapper.selectById(conversationId);
        if (conversation == null) {
            return;
        }

        List<ChatMessage> messages = messageMapper.selectList(
                new LambdaQueryWrapper<ChatMessage>()
                        .eq(ChatMessage::getConversationId, conversationId)
                        .eq(ChatMessage::getDeleted, false)
                        .orderByAsc(ChatMessage::getId));
        if (messages.isEmpty()) {
            return;
        }
        Long lastPos = conversation.getLastSummaryMessageId();
        // 双重边界：条数 OR Token。
        int msgCount = messages.size();
        long tokensSince = estimateTokensSince(messages, lastPos);
        boolean gapOk = (msgCount - safePos(lastPos)) >= properties.getGapCount() || tokensSince >= properties.getGapTokens();
        boolean thresholdOk = msgCount >= properties.getCountThreshold()
                || tokensSince >= properties.getTokenThreshold();
        if (!gapOk || !thresholdOk) {
            return;
        }
        // 待压缩消息 = 上次压缩之后。
        List<ChatMessage> toCompress = messages.stream()
                .filter(message -> lastPos == null || message.getId() > lastPos)
                .toList();
        if (toCompress.isEmpty()) {
            return;
        }
        // 调 Python 生成摘要（旧摘要合并）。
        String summary = summaryClient.summarize(
                toCompress,
                conversation.getSummary()
        );
        Long latestId = messages.get(messages.size() - 1).getId();
        // 乐观锁更新，防并发重复压缩。
        int rows = conversationMapper.update(null,
                Wrappers.<ChatConversation>lambdaUpdate()
                        .eq(ChatConversation::getId, conversationId)
                        .eq(ChatConversation::getLastSummaryMessageId, lastPos)
                        .set(ChatConversation::getSummary, summary)
                        .set(ChatConversation::getLastSummaryMessageId, latestId));
        if (rows == 1) {
            memoryCache.saveSummary(conversationId, summary);
            memoryCache.trimWorkingMemory(conversationId, properties.getKeepRecent());
            log.info("会话摘要已更新, conversationId={}, messages={}", conversationId, toCompress.size());
        }
    }
    /** 估算 lastPos 之后消息的 Token 总量（中英混合，字符数/2）。 */
    private long estimateTokensSince(List<ChatMessage> messages, Long lastPos) {
        long tokens = 0L;
        for (ChatMessage message : messages) {
            if (lastPos != null && message.getId() <= lastPos) {
                continue;
            }
            String content = message.getContent();
            tokens += (content == null ? 0 : (content.length() + 1) / 2);
        }
        return tokens;
    }

    private long safePos(Long lastPos) {
        return lastPos == null ? 0L : lastPos;
    }

}
