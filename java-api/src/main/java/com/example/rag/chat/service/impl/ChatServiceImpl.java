package com.example.rag.chat.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.rag.chat.client.PythonChatClient;
import com.example.rag.chat.client.dto.PythonChatData;
import com.example.rag.chat.client.dto.PythonChatRequest;
import com.example.rag.chat.client.sse.PythonChatStreamSession;
import com.example.rag.chat.client.sse.PythonSseEvent;
import com.example.rag.chat.dto.ChatConversationQueryRequest;
import com.example.rag.chat.dto.ChatRequest;
import com.example.rag.chat.dto.ChatResponse;
import com.example.rag.chat.dto.ChatStreamContext;
import com.example.rag.chat.entity.ChatConversation;
import com.example.rag.chat.entity.ChatMessage;
import com.example.rag.chat.mapper.ChatConversationMapper;
import com.example.rag.chat.mapper.ChatMessageMapper;
import com.example.rag.chat.service.ChatService;
import com.example.rag.chat.transaction.ChatPersistenceService;
import com.example.rag.common.api.PageResult;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.error.RemoteException;
import com.example.rag.common.id.IdGenerator;
import com.example.rag.common.security.CurrentUserProvider;
import com.example.rag.common.web.SseCloseReason;
import com.example.rag.common.web.SseEmitterSender;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Chat 业务服务实现。
 *
 * <p>Java 只负责会话创建、查询、权限校验和 Python 调用。
 * 聊天消息、摘要、last_route 和 Trace 均由 Python 持久化。</p>
 */
@Service
@Slf4j
public class ChatServiceImpl implements ChatService {

    private static final long SSE_TIMEOUT_MILLIS = 5 * 60 * 1000L;

    private final PythonChatClient pythonChatClient;
    private final ChatConversationMapper conversationMapper;
    private final ChatMessageMapper messageMapper;
    private final IdGenerator idGenerator;
    private final ObjectMapper objectMapper;
    private final ChatPersistenceService chatPersistenceService;
    private final Executor chatStreamExecutor;
    private final CurrentUserProvider currentUserProvider;

    public ChatServiceImpl(
            PythonChatClient pythonChatClient,
            ChatConversationMapper conversationMapper,
            ChatMessageMapper messageMapper,
            IdGenerator idGenerator,
            ObjectMapper objectMapper,
            ChatPersistenceService chatPersistenceService,
            @Qualifier("chatStreamExecutor") Executor chatStreamExecutor,
            CurrentUserProvider currentUserProvider
    ) {
        this.pythonChatClient = pythonChatClient;
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
        this.idGenerator = idGenerator;
        this.objectMapper = objectMapper;
        this.chatPersistenceService = chatPersistenceService;
        this.chatStreamExecutor = chatStreamExecutor;
        this.currentUserProvider = currentUserProvider;
    }

    @Override
    public ChatResponse chat(
            ChatRequest request
    ) throws JsonProcessingException {
        validateRequest(request);

        Long tenantId = currentUserProvider.requireTenantId();
        Long userId = currentUserProvider.requireUserId();
        Long traceId = idGenerator.nextId();
        String requestId = String.valueOf(traceId);

        ChatStreamContext context = chatPersistenceService.prepare(
                request,
                tenantId,
                userId,
                traceId,
                requestId
        );

        PythonChatData pythonData = pythonChatClient.chat(
                context.getPythonRequest()
        );
        validatePythonData(context, pythonData);

        return ChatResponse.builder()
                .conversationId(context.getConversationId())
                .traceId(traceId)
                .question(pythonData.getQuestion())
                .standaloneQuery(pythonData.getStandaloneQuery())
                .answerStatus(pythonData.getAnswerStatus())
                .answer(pythonData.getAnswer())
                .model(pythonData.getModel())
                .mode(pythonData.getMode())
                .intent(pythonData.getIntent())
                .needRag(pythonData.getNeedRag())
                .knowledgeBaseId(pythonData.getKnowledgeBaseId())
                .routeReason(pythonData.getRouteReason())
                .usedCitationIndexes(
                        pythonData.getUsedCitationIndexes()
                )
                .invalidCitationIndexes(
                        pythonData.getInvalidCitationIndexes()
                )
                .tokenUsage(pythonData.getTokenUsage())
                .citations(pythonData.getCitations())
                .build();
    }

    @Override
    public SseEmitter streamChat(ChatRequest request) {
        validateRequest(request);

        Long tenantId = currentUserProvider.requireTenantId();
        Long userId = currentUserProvider.requireUserId();
        Long traceId = idGenerator.nextId();
        String requestId = String.valueOf(traceId);

        ChatStreamContext streamContext =
                chatPersistenceService.prepare(
                        request,
                        tenantId,
                        userId,
                        traceId,
                        requestId
                );

        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MILLIS);
        PythonChatStreamSession streamSession =
                new PythonChatStreamSession();
        SseEmitterSender sender = new SseEmitterSender(
                emitter,
                reason -> {
                    log.debug(
                            "SSE 关闭, traceId={}, reason={}",
                            traceId,
                            reason
                    );
                    streamSession.cancel();
                }
        );
        AtomicBoolean finalReceived = new AtomicBoolean(false);

        try {
            chatStreamExecutor.execute(() -> {
                try {
                    pythonChatClient.streamChat(
                            streamContext.getPythonRequest(),
                            event -> {
                                if (sender.isOpen()) {
                                    handlePythonStreamEvent(
                                            event,
                                            streamContext,
                                            sender,
                                            finalReceived
                                    );
                                }
                            },
                            streamSession
                    );

                    if (!finalReceived.get()) {
                        throw new IllegalStateException(
                                "Python SSE stream ended without final event"
                        );
                    }

                    sender.complete();
                } catch (Exception exception) {
                    handleStreamException(
                            exception,
                            sender,
                            streamContext
                    );
                }
            });
        } catch (RejectedExecutionException exception) {
            sender.send(
                    "error",
                    Map.of(
                            "code", "CHAT_EXECUTOR_REJECTED",
                            "message", "聊天线程池繁忙",
                            "traceId", traceId
                    )
            );
            sender.complete();
            throw exception;
        }

        return emitter;
    }

    private void handlePythonStreamEvent(
            PythonSseEvent event,
            ChatStreamContext streamContext,
            SseEmitterSender sender,
            AtomicBoolean finalReceived
    ) {
        String eventName = event.getEvent();
        JsonNode eventData = event.getData();

        switch (eventName) {
            case "final" -> handleFinalEvent(
                    eventData,
                    streamContext,
                    sender,
                    finalReceived
            );
            case "error" -> throw new PythonStreamException(
                    eventData.path("message")
                            .asText("Python Chat 流式处理失败"),
                    sender.send("error", eventData)
            );
            default -> sender.send(eventName, eventData);
        }
    }

    private void handleFinalEvent(
            JsonNode eventData,
            ChatStreamContext streamContext,
            SseEmitterSender sender,
            AtomicBoolean finalReceived
    ) {
        if (finalReceived.get()) {
            return;
        }

        try {
            PythonChatData pythonData = objectMapper.treeToValue(
                    eventData,
                    PythonChatData.class
            );
            validatePythonData(streamContext, pythonData);
            finalReceived.set(true);
            sender.send("final", eventData);
        } catch (Exception exception) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "校验 Python 流式聊天最终结果失败",
                    exception
            );
        }
    }

    private void handleStreamException(
            Exception exception,
            SseEmitterSender sender,
            ChatStreamContext streamContext
    ) {
        SseCloseReason reason = sender.getCloseReason();
        Long traceId = streamContext.getTraceId();

        if (reason == SseCloseReason.COMPLETED) {
            return;
        }
        if (reason == SseCloseReason.CLIENT_DISCONNECTED) {
            log.info("客户端取消流式 Chat, traceId={}", traceId);
            return;
        }
        if (reason == SseCloseReason.TIMEOUT) {
            log.warn("流式 Chat 超时, traceId={}", traceId);
            return;
        }

        log.error("Java 流式 Chat 处理失败, traceId={}", traceId, exception);

        boolean errorAlreadyForwarded =
                exception instanceof PythonStreamException streamException
                        && streamException.isErrorForwarded();

        if (!errorAlreadyForwarded && sender.isOpen()) {
            sender.send(
                    "error",
                    Map.of(
                            "code", "JAVA_STREAM_FAILED",
                            "message", safeErrorMessage(exception),
                            "traceId", traceId
                    )
            );
        }
        sender.complete();
    }

    private void validatePythonData(
            ChatStreamContext context,
            PythonChatData pythonData
    ) {
        if (pythonData == null) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python Chat 服务未返回数据"
            );
        }
        if (pythonData.getTraceId() == null
                || !context.getTraceId().equals(
                pythonData.getTraceId()
        )) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python Chat 服务返回的 Trace ID 不一致"
            );
        }
        if (pythonData.getConversationId() == null
                || !context.getConversationId().equals(
                pythonData.getConversationId()
        )) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python Chat 服务返回的会话 ID 不一致"
            );
        }
    }

    private String safeErrorMessage(Throwable exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) {
            return "流式聊天处理失败";
        }
        return limitText(message, 500);
    }

    private String limitText(String text, int maxLength) {
        if (text == null || text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength);
    }

    private static final class PythonStreamException
            extends RuntimeException {

        private final boolean errorForwarded;

        private PythonStreamException(
                String message,
                boolean errorForwarded
        ) {
            super(message);
            this.errorForwarded = errorForwarded;
        }

        private boolean isErrorForwarded() {
            return errorForwarded;
        }
    }

    @Override
    public PageResult<ChatConversation> pageConversations(
            ChatConversationQueryRequest request
    ) {
        Long tenantId = currentUserProvider.requireTenantId();
        Long userId = currentUserProvider.requireUserId();
        ChatConversationQueryRequest pageRequest =
                request == null
                        ? new ChatConversationQueryRequest()
                        : request;

        LambdaQueryWrapper<ChatConversation> wrapper =
                new LambdaQueryWrapper<ChatConversation>()
                        .eq(ChatConversation::getTenantId, tenantId)
                        .eq(ChatConversation::getUserId, userId)
                        .orderByDesc(ChatConversation::getUpdatedAt);

        if (request != null && request.getKnowledgeBaseId() != null) {
            wrapper.eq(
                    ChatConversation::getKnowledgeBaseId,
                    request.getKnowledgeBaseId()
            );
        }
        if (request != null && StringUtils.hasText(request.getKeyword())) {
            wrapper.like(
                    ChatConversation::getTitle,
                    request.getKeyword()
            );
        }

        Page<ChatConversation> page = conversationMapper.selectPage(
                new Page<>(
                        pageRequest.normalizedPageNo(),
                        pageRequest.normalizedPageSize()
                ),
                wrapper
        );
        return PageResult.from(page);
    }

    @Override
    public ChatConversation getConversation(Long conversationId) {
        return requireCurrentTenantConversation(conversationId);
    }

    @Override
    public List<ChatMessage> listMessages(Long conversationId) {
        requireCurrentTenantConversation(conversationId);
        return messageMapper.selectList(
                new LambdaQueryWrapper<ChatMessage>()
                        .eq(
                                ChatMessage::getConversationId,
                                conversationId
                        )
                        .eq(ChatMessage::getDeleted, false)
                        .orderByAsc(ChatMessage::getCreatedAt)
        );
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteConversation(Long conversationId) {
        ChatConversation conversation =
                requireCurrentTenantConversation(conversationId);

        messageMapper.delete(
                new LambdaQueryWrapper<ChatMessage>()
                        .eq(
                                ChatMessage::getConversationId,
                                conversation.getId()
                        )
        );
        conversationMapper.deleteById(conversation.getId());
    }

    private ChatConversation requireCurrentTenantConversation(
            Long conversationId
    ) {
        if (conversationId == null) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "会话 ID 不能为空"
            );
        }

        ChatConversation conversation =
                conversationMapper.selectById(conversationId);
        validateTenantConversation(
                conversation,
                currentUserProvider.requireTenantId(),
                currentUserProvider.requireUserId()
        );
        return conversation;
    }

    private void validateTenantConversation(
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
                    "无权访问该会话"
            );
        }
        if (!userId.equals(conversation.getUserId())) {
            throw new ClientException(
                    BaseErrorCode.FORBIDDEN,
                    "无权访问其他用户的会话"
            );
        }
    }

    private void validateRequest(ChatRequest request) {
        if (
                request == null
                        || !StringUtils.hasText(request.getQuestion())
        ) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "问题不能为空"
            );
        }
    }
}
