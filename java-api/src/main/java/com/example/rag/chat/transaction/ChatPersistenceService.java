package com.example.rag.chat.transaction;

import com.example.rag.chat.client.dto.PythonChatRequest;
import com.example.rag.chat.dto.ChatRequest;
import com.example.rag.chat.dto.ChatStreamContext;
import com.example.rag.chat.entity.ChatConversation;
import com.example.rag.chat.mapper.ChatConversationMapper;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.id.IdGenerator;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Java 侧聊天准备事务。
 *
 * <p>Python 是聊天消息、摘要、last_route 和 Trace 的唯一写入方。
 * Java 这里只负责创建或校验会话，并构造最小 Python 请求。</p>
 */
@Service
@RequiredArgsConstructor
public class ChatPersistenceService {

    private final ChatConversationMapper conversationMapper;
    private final IdGenerator idGenerator;

    @Transactional(rollbackFor = Exception.class)
    public ChatStreamContext prepare(
            ChatRequest request,
            Long tenantId,
            Long userId,
            Long traceId,
            String requestId
    ) {
        ChatConversation conversation = getOrCreateConversation(
                request,
                tenantId,
                userId
        );

        PythonChatRequest pythonRequest = new PythonChatRequest();
        pythonRequest.setQuestion(request.getQuestion());
        pythonRequest.setModel(request.getModel());
        pythonRequest.setTenantId(tenantId);
        pythonRequest.setUserId(userId);
        pythonRequest.setTraceId(traceId);
        pythonRequest.setRequestId(requestId);
        pythonRequest.setConversationId(conversation.getId());
        pythonRequest.setKnowledgeBaseId(request.getKnowledgeBaseId());

        return ChatStreamContext.builder()
                .tenantId(tenantId)
                .userId(userId)
                .conversationId(conversation.getId())
                .traceId(traceId)
                .requestId(requestId)
                .pythonRequest(pythonRequest)
                .build();
    }

    private ChatConversation getOrCreateConversation(
            ChatRequest request,
            Long tenantId,
            Long userId
    ) {
        if (request.getConversationId() != null) {
            ChatConversation conversation =
                    conversationMapper.selectById(
                            request.getConversationId()
                    );
            validateConversation(
                    conversation,
                    tenantId,
                    userId
            );
            return conversation;
        }

        ChatConversation conversation =
                ChatConversation.builder()
                        .id(idGenerator.nextId())
                        .tenantId(tenantId)
                        .userId(userId)
                        .knowledgeBaseId(
                                request.getKnowledgeBaseId()
                        )
                        .title(buildTitle(request.getQuestion()))
                        .channel("WEB")
                        .metadata("{}")
                        .build();

        conversationMapper.insert(conversation);
        return conversation;
    }

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

        if (!tenantId.equals(conversation.getTenantId())) {
            throw new ClientException(
                    BaseErrorCode.FORBIDDEN,
                    "无权访问该租户的会话"
            );
        }

        if (!userId.equals(conversation.getUserId())) {
            throw new ClientException(
                    BaseErrorCode.FORBIDDEN,
                    "无权访问其他用户的会话"
            );
        }
    }

    private String buildTitle(String question) {
        String normalized = question.trim();
        return normalized.length() <= 30
                ? normalized
                : normalized.substring(0, 30);
    }
}
