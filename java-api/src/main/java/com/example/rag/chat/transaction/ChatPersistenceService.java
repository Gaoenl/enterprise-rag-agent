package com.example.rag.chat.transaction;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.rag.chat.client.dto.PythonChatData;
import com.example.rag.chat.client.dto.PythonChatHistoryMessage;
import com.example.rag.chat.client.dto.PythonChatRequest;
import com.example.rag.chat.config.ConversationMemoryCache;
import com.example.rag.chat.dto.ChatRequest;
import com.example.rag.chat.dto.ChatStreamContext;
import com.example.rag.chat.entity.ChatConversation;
import com.example.rag.chat.entity.ChatMessage;
import com.example.rag.chat.mapper.ChatConversationMapper;
import com.example.rag.chat.mapper.ChatMessageMapper;
import com.example.rag.chat.service.ConversationSummaryService;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.id.IdGenerator;
import com.example.rag.trace.service.RagTraceService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 流式聊天数据库事务服务。
 *
 * <p>所有数据库写操作都放在短事务中，不在该类中调用 Python。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ChatPersistenceService {

    private static final int HISTORY_LIMIT = 10;

    private final ChatConversationMapper conversationMapper;
    private final ChatMessageMapper messageMapper;
    private final RagTraceService ragTraceService;
    private final IdGenerator idGenerator;
    private final ObjectMapper objectMapper;
    private final ConversationMemoryCache memoryCache;
    private final ConversationSummaryService summaryService;

    /**
     * 创建流式请求需要的数据库数据。
     *
     * <p>事务提交后才允许开始调用 Python，确保用户消息
     * 不会因为 SSE 连接持续时间较长而一直处于未提交状态。</p>
     */
    @Transactional(rollbackFor = Exception.class)
    public ChatStreamContext prepare(
            ChatRequest request,
            Long tenantId,
            Long userId,
            Long traceId,
            String requestId
    ) {
        // 获取已有会话，或者创建新会话。
        ChatConversation conversation =
                getOrCreateConversation(
                        request,
                        tenantId,
                        userId
                );

        // 在保存当前问题前查询历史，避免把本轮问题重复放入 history。
        List<ChatMessage> recentMessages =
                listRecentMessages(
                        conversation.getId()
                );

        // 保存本轮用户问题。
        ChatMessage userMessage =
                saveUserMessage(
                        conversation.getId(),
                        tenantId,
                        request.getQuestion()
                );
        summaryService.triggerAfterCommit(conversation.getId());
        memoryCache.pushMessage(conversation.getId(), "user", request.getQuestion());


        // 将数据库消息转换成 Python 请求格式。
        List<PythonChatHistoryMessage> history =
                recentMessages.stream()
                        .map(message ->
                                PythonChatHistoryMessage
                                        .builder()
                                        .role(message.getRole())
                                        .content(
                                                message.getContent()
                                        )
                                        .build()
                        )
                        .toList();

        // 构建发送给 Python 的请求。
        PythonChatRequest pythonRequest =
                new PythonChatRequest();

        // 设置用户当前问题。
        pythonRequest.setQuestion(
                request.getQuestion()
        );

        // 设置可选模型名称。
        pythonRequest.setModel(
                request.getModel()
        );

        // tenantId 必须来自 Java 登录上下文。
        pythonRequest.setTenantId(tenantId);

        // userId 必须来自 Java 登录上下文。
        pythonRequest.setUserId(userId);

        // 设置 Java 生成的 Trace ID。
        pythonRequest.setTraceId(traceId);

        // 设置日志关联 ID。
        pythonRequest.setRequestId(requestId);

        // 设置当前会话 ID。
        pythonRequest.setConversationId(
                conversation.getId()
        );

        // 设置用户选择的知识库 ID。
        pythonRequest.setKnowledgeBaseId(
                request.getKnowledgeBaseId()
        );

        // 设置已持久化的最近会话历史。
        pythonRequest.setHistory(history);
        // 摘要读取 Redis 优先，未命中回退 PG。
        String summary = memoryCache.getSummary(conversation.getId());
        pythonRequest.setSummary(
                summary != null ? summary : conversation.getSummary()
        );
        // 返回流式过程内部上下文。
        return ChatStreamContext.builder()
                .tenantId(tenantId)
                .userId(userId)
                .conversationId(
                        conversation.getId()
                )
                .userMessageId(
                        userMessage.getId()
                )
                .traceId(traceId)
                .requestId(requestId)
                .pythonRequest(pythonRequest)
                .build();
    }

    /**
     * 保存 Python final 事件中的最终结果。
     *
     * <p>只有收到 final 后才调用该方法。delta 事件不能入库，
     * 因为 final 可能经过引用校验和回答后处理。</p>
     */
    @Transactional(rollbackFor = Exception.class)
    public ChatMessage saveFinalResult(
            ChatStreamContext context,
            PythonChatData pythonData
    ) throws JsonProcessingException {
        // 校验 Python 返回的 Trace ID。
        validateTraceId(
                context.getTraceId(),
                pythonData
        );

        // 将引用信息序列化为 JSONB 字符串。
        String citationsJson =
                objectMapper.writeValueAsString(
                        pythonData.getCitations() == null
                                ? List.of()
                                : pythonData.getCitations()
                );

        // 将 Token 用量序列化为 JSONB 字符串。
        String tokenUsageJson =
                objectMapper.writeValueAsString(
                        pythonData.getTokenUsage() == null
                                ? Map.of()
                                : pythonData.getTokenUsage()
                );

        // 保存最终助手消息。
        ChatMessage assistantMessage =
                ChatMessage.builder()
                        .id(idGenerator.nextId())
                        .tenantId(
                                context.getTenantId()
                        )
                        .conversationId(
                                context.getConversationId()
                        )
                        .parentMessageId(
                                context.getUserMessageId()
                        )
                        .role("ASSISTANT")
                        .content(
                                pythonData.getAnswer()
                        )
                        .citations(citationsJson)
                        .tokenUsage(tokenUsageJson)
                        .traceId(
                                context.getTraceId()
                        )
                        .build();

        // 插入助手消息。
        messageMapper.insert(assistantMessage);

        // 保存 Python 返回的完整成功 Trace。
        ragTraceService.saveSuccessTrace(
                context.getTenantId(),
                context.getConversationId(),
                assistantMessage.getId(),
                pythonData.getTrace()
        );

        // 如果 Python 实际选择了知识库，则更新会话绑定。
        updateConversationKnowledgeBase(
                context.getConversationId(),
                pythonData.getKnowledgeBaseId()
        );

        return assistantMessage;
    }

    /**
     * 使用独立事务保存失败 Trace。
     *
     * <p>即使外层流式调用失败，本事务也可以单独提交。</p>
     */
    @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            rollbackFor = Exception.class
    )
    public void saveFailedTrace(
            ChatStreamContext context,
            ChatRequest request,
            Throwable exception
    ) {
        // 使用 HashMap，因为 knowledgeBaseId 可能为空。
        Map<String, Object> input = new HashMap<>();

        // 记录会话 ID。
        input.put(
                "conversationId",
                context.getConversationId()
        );

        // 记录本轮用户消息 ID。
        input.put(
                "userMessageId",
                context.getUserMessageId()
        );

        // 记录请求知识库 ID。
        input.put(
                "knowledgeBaseId",
                request.getKnowledgeBaseId()
        );

        // 限制 Trace 中保存的问题长度。
        input.put(
                "question",
                limitText(
                        request.getQuestion(),
                        1000
                )
        );

        // 保存失败 Trace。
        ragTraceService.saveFailedTrace(
                context.getTraceId(),
                context.getTenantId(),
                context.getRequestId(),
                input,
                exception
        );
    }

    /**
     * 获取已有会话或创建新会话。
     */
    private ChatConversation getOrCreateConversation(
            ChatRequest request,
            Long tenantId,
            Long userId
    ) {
        // conversationId 不为空时使用已有会话。
        if (request.getConversationId() != null) {
            ChatConversation conversation =
                    conversationMapper.selectById(
                            request.getConversationId()
                    );

            // 校验会话属于当前租户和用户。
            validateConversation(
                    conversation,
                    tenantId,
                    userId
            );

            return conversation;
        }

        // 创建新会话。
        ChatConversation conversation =
                ChatConversation.builder()
                        .id(idGenerator.nextId())
                        .tenantId(tenantId)
                        .userId(userId)
                        .knowledgeBaseId(
                                request.getKnowledgeBaseId()
                        )
                        .title(
                                buildTitle(
                                        request.getQuestion()
                                )
                        )
                        .channel("WEB")
                        .metadata("{}")
                        .build();

        // 保存新会话。
        conversationMapper.insert(conversation);

        return conversation;
    }

    /**
     * 保存用户问题消息。
     */
    private ChatMessage saveUserMessage(
            Long conversationId,
            Long tenantId,
            String question
    ) {
        ChatMessage message =
                ChatMessage.builder()
                        .id(idGenerator.nextId())
                        .tenantId(tenantId)
                        .conversationId(conversationId)
                        .role("USER")
                        .content(question)
                        .citations("[]")
                        .tokenUsage("{}")
                        .build();

        // 插入用户消息。
        messageMapper.insert(message);

        return message;
    }

    /**
     * 查询最近的会话消息。
     */
    private List<ChatMessage> listRecentMessages(
            Long conversationId
    ) {
        // 1. 优先读 Redis 工作记忆（命中即返回，省 PG 查询）。
        List<ChatMessage> cached = memoryCache.getRecentMessages(
                conversationId, HISTORY_LIMIT
        );
        if (!cached.isEmpty()) {
            return cached;
        }

        // 2. 未命中：先按时间倒序查询最近 N 条消息。
        // 先按时间倒序查询最近 N 条消息。
        List<ChatMessage> messages =
                messageMapper.selectList(
                        new LambdaQueryWrapper<ChatMessage>()
                                .eq(
                                        ChatMessage::getConversationId,
                                        conversationId
                                )
                                .eq(
                                        ChatMessage::getDeleted,
                                        false
                                )
                                .orderByDesc(
                                        ChatMessage::getCreatedAt
                                )
                                .last(
                                        "LIMIT " + HISTORY_LIMIT
                                )
                );

        // 3. 恢复成真实对话顺序，并回填 Redis（从旧到新，leftPush 后最新在前）。
        List<ChatMessage> ordered = messages.stream()
                .sorted(
                        Comparator.comparing(
                                ChatMessage::getCreatedAt
                        )
                )
                .toList();
        for (ChatMessage message : ordered) {
            memoryCache.pushMessage(
                    conversationId,
                    message.getRole(),
                    message.getContent()
            );
        }
        return ordered;
    }

    /**
     * 更新会话实际使用的知识库。
     */
    private void updateConversationKnowledgeBase(
            Long conversationId,
            Long knowledgeBaseId
    ) {
        // 普通聊天或澄清响应可能没有知识库 ID。
        if (knowledgeBaseId == null) {
            return;
        }

        ChatConversation conversation =
                conversationMapper.selectById(
                        conversationId
                );

        if (conversation == null) {
            throw new ClientException(
                    BaseErrorCode.NOT_FOUND,
                    "会话不存在"
            );
        }

        // 更新 Python 最终选中的知识库。
        conversation.setKnowledgeBaseId(
                knowledgeBaseId
        );

        // 更新会话。
        conversationMapper.updateById(
                conversation
        );
    }

    /**
     * 校验会话访问边界。
     */
    private void validateConversation(
            ChatConversation conversation,
            Long tenantId,
            Long userId
    ) {
        if (
                conversation == null
                        || Boolean.TRUE.equals(
                        conversation.getDeleted()
                )
        ) {
            throw new ClientException(
                    BaseErrorCode.NOT_FOUND,
                    "会话不存在"
            );
        }

        if (!tenantId.equals(
                conversation.getTenantId()
        )) {
            throw new ClientException(
                    BaseErrorCode.FORBIDDEN,
                    "无权访问该租户的会话"
            );
        }

        if (!userId.equals(
                conversation.getUserId()
        )) {
            throw new ClientException(
                    BaseErrorCode.FORBIDDEN,
                    "无权访问其他用户的会话"
            );
        }
    }

    /**
     * 校验 Python 返回的 Trace ID。
     */
    private void validateTraceId(
            Long expectedTraceId,
            PythonChatData pythonData
    ) {
        if (pythonData == null) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "Python 未返回最终聊天数据"
            );
        }

        if (pythonData.getTraceId() == null) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "Python 未返回 Trace ID"
            );
        }

        if (!expectedTraceId.equals(
                pythonData.getTraceId()
        )) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "Python 返回的 Trace ID 不一致"
            );
        }
    }

    /**
     * 根据问题生成会话标题。
     */
    private String buildTitle(String question) {
        String normalized = question.trim();

        if (normalized.length() <= 30) {
            return normalized;
        }

        return normalized.substring(0, 30);
    }

    /**
     * 限制 Trace 文本长度。
     */
    private String limitText(
            String text,
            int maxLength
    ) {
        if (text == null) {
            return null;
        }

        if (text.length() <= maxLength) {
            return text;
        }

        return text.substring(0, maxLength);
    }
}
