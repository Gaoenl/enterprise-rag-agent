package com.example.rag.chat.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.rag.chat.client.PythonChatClient;
import com.example.rag.chat.client.dto.PythonChatData;
import com.example.rag.chat.client.dto.PythonChatHistoryMessage;
import com.example.rag.chat.client.dto.PythonChatRequest;
import com.example.rag.chat.client.sse.PythonChatStreamSession;
import com.example.rag.chat.client.sse.PythonSseEvent;
import com.example.rag.chat.config.ConversationMemoryCache;
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
import com.example.rag.common.context.LoginUser;
import com.example.rag.common.context.UserContext;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.error.RemoteException;
import com.example.rag.common.id.IdGenerator;
import com.example.rag.common.security.CurrentUserProvider;
import com.example.rag.common.web.SseCloseReason;
import com.example.rag.common.web.SseEmitterSender;
import com.example.rag.trace.service.RagTraceService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Chat 业务服务实现。
 */
@Service
@Slf4j
public class ChatServiceImpl implements ChatService {

    private static final int HISTORY_LIMIT = 10;
    private static final long SSE_TIMEOUT_MILLIS = 5 * 60 * 1000L;

    private final PythonChatClient pythonChatClient;
    private final ChatConversationMapper conversationMapper;
    private final ChatMessageMapper messageMapper;
    private final IdGenerator idGenerator;
    private final ObjectMapper objectMapper;
    private final RagTraceService ragTraceService;
    private final ChatPersistenceService chatPersistenceService;
    private final Executor chatStreamExecutor;
    private final CurrentUserProvider currentUserProvider;
    private final ConversationMemoryCache memoryCache;

    public ChatServiceImpl(PythonChatClient pythonChatClient,
                           ChatConversationMapper conversationMapper,
                           ChatMessageMapper messageMapper,
                           IdGenerator idGenerator,
                           ObjectMapper objectMapper,
                           RagTraceService ragTraceService,
                           ChatPersistenceService chatPersistenceService,
                           @Qualifier("chatStreamExecutor") Executor chatStreamExecutor,
                           CurrentUserProvider currentUserProvider,
                           ConversationMemoryCache memoryCache) {
        this.pythonChatClient = pythonChatClient;
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
        this.idGenerator = idGenerator;
        this.objectMapper = objectMapper;
        this.ragTraceService = ragTraceService;
        this.chatPersistenceService = chatPersistenceService;
        this.chatStreamExecutor = chatStreamExecutor;
        this.currentUserProvider = currentUserProvider;
        this.memoryCache = memoryCache;
    }



    @Override
    @Transactional(rollbackFor = Exception.class)
    public ChatResponse chat(ChatRequest request) throws JsonProcessingException {
        // 校验用户问题，避免空问题进入会话和模型链路。
        validateRequest(request);

        // 读取当前请求上下文，用于绑定租户、用户和权限边界。
        Long tenantId = currentUserProvider.requireTenantId();
        Long userId = currentUserProvider.requireUserId();
        // 为本次 RAG 请求生成唯一 Trace 主键。
        Long traceId = idGenerator.nextId();

        // 生成跨 Java 和 Python 日志使用的请求 ID。
        String requestId = String.valueOf(traceId);
        PythonChatRequest pythonRequest=new PythonChatRequest();

        // 获取已有会话，或者为本次提问创建新会话。
        ChatConversation conversation = getOrCreateConversation(request, tenantId, userId);

        // 查询本轮提问之前的最近历史消息，用于 Python 侧组装多轮上下文。
        List<ChatMessage> recentMessages = listRecentMessages(conversation.getId());

        // 保存用户问题消息，后续用于会话历史、审计和多轮上下文。
        ChatMessage userMessage = saveUserMessage(conversation.getId(), tenantId, request.getQuestion());

        // 将 Java 消息实体转换为 Python Chat history 请求结构。
        List<PythonChatHistoryMessage> history = recentMessages.stream()
                .map(message -> PythonChatHistoryMessage.builder()
                        .role(message.getRole())
                        .content(message.getContent())
                        .build())
                .toList();
        // 设置当前用户的原始问题。
        pythonRequest.setQuestion(request.getQuestion());

        // 设置用户本次选择的模型。
        pythonRequest.setModel(request.getModel());

        // 从用户上下文设置租户 ID，不能使用前端伪造值。
        pythonRequest.setTenantId(tenantId);

        // 从用户上下文设置当前用户 ID。
        pythonRequest.setUserId(userId);
        // 将 Trace ID 传给 Python，由 Python 原样返回。
        pythonRequest.setTraceId(traceId);
        // 将请求关联 ID 传给 Python。
        pythonRequest.setRequestId(requestId);

        // 设置当前已经创建或查询到的会话 ID。
        pythonRequest.setConversationId(conversation.getId());

        // 摘要读取 Redis 优先，未命中回退 PG。
        String summary = memoryCache.getSummary(conversation.getId());
        pythonRequest.setSummary(
                summary != null ? summary : conversation.getSummary()
        );

        // 设置用户明确选择的知识库 ID。
        pythonRequest.setKnowledgeBaseId(request.getKnowledgeBaseId());

        // 设置从数据库加载并转换后的会话历史。
        pythonRequest.setHistory(history);


        // 调用 Python Chat 服务，Python 会使用 history 生成多轮回答。
        PythonChatData pythonData;
        try {
            // 调用 Python RAG 服务。
            pythonData = pythonChatClient.chat(
                    pythonRequest
            );
        } catch (Exception exception) {
            // Python 调用失败时，独立保存失败 Trace。
            saveFailedTraceSafely(
                    traceId,
                    tenantId,
                    requestId,
                    conversation.getId(),
                    request,
                    exception
            );
            // 继续抛出原异常，交给全局异常处理器。
            throw exception;
        }
        // 校验 Python 返回的 Trace ID 与 Java 请求一致。
        validatePythonTraceId(
                traceId,
                pythonData
        );

        // 将引用信息转换为 JSONB 字符串。
        String citationsJson = objectMapper.writeValueAsString(
                pythonData.getCitations() == null
                        ? List.of()
                        : pythonData.getCitations()
        );

    // 将 Token 用量转换为 JSONB 字符串。
        String tokenUsageJson = objectMapper.writeValueAsString(
                pythonData.getTokenUsage() == null
                        ? Map.of()
                        : pythonData.getTokenUsage()
        );
        // 保存助手消息，并关联本次 RAG Trace。
        ChatMessage assistantMessage = saveAssistantMessage(
                conversation.getId(),
                tenantId,
                userMessage.getId(),
                pythonData.getAnswer(),
                citationsJson,
                tokenUsageJson,
                traceId
        );
        // 将 Python 返回的完整 Trace 保存到 rag_trace。
        ragTraceService.saveSuccessTrace(
                tenantId,
                conversation.getId(),
                assistantMessage.getId(),
                pythonData.getTrace()
        );

        // 返回前端展示和继续追问所需的会话、消息与回答信息。
        return ChatResponse.builder()
                // 返回当前会话 ID。
                .conversationId(conversation.getId())
                .traceId(traceId)
                // 返回用户原始问题。
                .question(pythonData.getQuestion())
                // 返回问题独立化结果。
                .standaloneQuery(pythonData.getStandaloneQuery())
                .answerStatus(pythonData.getAnswerStatus())
                // 返回模型最终回答。
                .answer(pythonData.getAnswer())
                // 返回实际模型。
                .model(pythonData.getModel())
                // 返回基础问答、RAG 或澄清模式。
                .mode(pythonData.getMode())
                // 返回路由识别出的意图。
                .intent(pythonData.getIntent())
                // 返回是否执行了知识库检索。
                .needRag(pythonData.getNeedRag())
                // 返回实际选中的知识库。
                .knowledgeBaseId(pythonData.getKnowledgeBaseId())
                // 返回路由或选择原因。
                .routeReason(pythonData.getRouteReason())
                .usedCitationIndexes(pythonData.getUsedCitationIndexes())
                .invalidCitationIndexes(pythonData.getInvalidCitationIndexes())
                .tokenUsage(pythonData.getTokenUsage())
                // 返回回答引用的文档分片。
                .citations(pythonData.getCitations())
                .build();
    }

    @Override
    public SseEmitter streamChat(ChatRequest request) {
        // 在建立 SSE 连接前完成参数与登录上下文校验。
        validateRequest(request);
        Long tenantId = currentUserProvider.requireTenantId();
        Long userId = currentUserProvider.requireUserId();

        // Java 生成 Trace ID，并用它关联 Java 与 Python 日志。
        Long traceId = idGenerator.nextId();
        String requestId = String.valueOf(traceId);

        // 使用短事务创建或校验会话、读取历史并保存用户消息。
        ChatStreamContext streamContext = chatPersistenceService.prepare(
                request, tenantId, userId, traceId, requestId
        );

        // 创建前端 SSE、Python 下游取消句柄和事件发送器。
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MILLIS);
        PythonChatStreamSession streamSession = new PythonChatStreamSession();
        SseEmitterSender sender = new SseEmitterSender(
                emitter,
                reason -> {
                    // Sender 保留具体关闭原因，回调只负责释放 Python 响应流。
                    log.debug("SSE 关闭, traceId={}, reason={}", traceId, reason);
                    streamSession.cancel();
                }
        );

        // 只有 final 数据成功入库后才设置为 true。
        AtomicBoolean finalPersisted = new AtomicBoolean(false);

        // Python Client 会阻塞读取 SSE，因此放入专用线程池。
        try{
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
                                            finalPersisted
                                    );
                                }
                            },
                            streamSession
                    );

                    // 流正常结束却没有成功入库 final，属于协议失败。
                    if (!finalPersisted.get()) {
                        throw new IllegalStateException(
                                "Python SSE stream ended without persisted final event"
                        );
                    }

                    // complete() 会先记录 COMPLETED，再触发取消句柄。
                    sender.complete();
                } catch (Exception exception) {
                    handleStreamException(
                            exception,
                            request,
                            streamContext,
                            sender,
                            finalPersisted
                    );
                }
            });
        }catch (RejectedExecutionException ex){
            saveStreamFailedTraceSafely(streamContext,request,ex);
            emitter.completeWithError(ex);
            throw ex;
        }

        return emitter;
    }

    /**
     * 根据事件名称处理 Python 返回的单个 SSE 事件。
     */
    private void handlePythonStreamEvent(
            PythonSseEvent event,
            ChatStreamContext streamContext,
            SseEmitterSender sender,
            AtomicBoolean finalPersisted
    ) {
        String eventName = event.getEvent();
        JsonNode eventData = event.getData();

        switch (eventName) {
            case "final" -> handleFinalEvent(
                    eventData, streamContext, sender, finalPersisted
            );
            case "error" -> handlePythonErrorEvent(eventData, sender);
            case "done" -> {
                // done 只转发，外层确认 final 已入库后再关闭连接。
                sender.send("done", eventData);
            }
            default -> {
                // 原样转发 start、route、retrieval、delta 和 heartbeat。
                sender.send(eventName, eventData);
            }
        }
    }

    /**
     * 使用短事务保存 final，并在成功后把权威结果转发给前端。
     */
    private void handleFinalEvent(
            JsonNode eventData,
            ChatStreamContext streamContext,
            SseEmitterSender sender,
            AtomicBoolean finalPersisted
    ) {
        // Parser 顺序回调；已成功处理 final 时忽略重复事件。
        if (finalPersisted.get()) {
            log.warn("忽略重复 final, traceId={}", streamContext.getTraceId());
            return;
        }

        try {
            PythonChatData pythonData = objectMapper.treeToValue(
                    eventData, PythonChatData.class
            );

            // 保存助手消息、引用、Token 用量和成功 Trace。
            chatPersistenceService.saveFinalResult(streamContext, pythonData);

            // 事务成功后再标记，不能在数据库保存前提前设置。
            finalPersisted.set(true);
            sender.send("final", eventData);
        } catch (Exception exception) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "保存流式聊天最终结果失败",
                    exception
            );
        }
    }

    /**
     * 转发 Python error，并抛出异常交给流式线程统一保存失败 Trace。
     */
    private void handlePythonErrorEvent(
            JsonNode eventData,
            SseEmitterSender sender
    ) {
        boolean forwarded = sender.send("error", eventData);
        String message = eventData.path("message")
                .asText("Python Chat 流式处理失败");
        throw new PythonStreamException(message, forwarded);
    }

    /**
     * 根据 Sender 保存的关闭原因统一处理异常。
     */
    private void handleStreamException(
            Exception exception,
            ChatRequest request,
            ChatStreamContext streamContext,
            SseEmitterSender sender,
            AtomicBoolean finalPersisted
    ) {
        SseCloseReason reason = sender.getCloseReason();
        Long traceId = streamContext.getTraceId();

        // 正常完成后的下游关闭异常不属于业务失败。
        if (reason == SseCloseReason.COMPLETED) {
            log.debug("流式 Chat 已正常完成, traceId={}", traceId);
            return;
        }

        // 客户端取消时不再向已经关闭的连接发送 error。
        if (reason == SseCloseReason.CLIENT_DISCONNECTED) {
            log.info("客户端取消流式 Chat, traceId={}", traceId);
            if (!finalPersisted.get()) {
                saveStreamFailedTraceSafely(
                        streamContext,
                        request,
                        new IllegalStateException(
                                "Chat stream cancelled by client", exception
                        )
                );
            }
            return;
        }

        // 超时由 Sender 关闭前端 SSE，并通过取消句柄关闭 Python 流。
        if (reason == SseCloseReason.TIMEOUT) {
            log.warn("流式 Chat 超时, traceId={}", traceId);
            if (!finalPersisted.get()) {
                saveStreamFailedTraceSafely(
                        streamContext,
                        request,
                        new IllegalStateException("Chat stream timeout", exception)
                );
            }
            return;
        }

        log.error("Java 流式 Chat 处理失败, traceId={}", traceId, exception);

        // final 已成功入库时不能再写失败 Trace。
        if (!finalPersisted.get()) {
            saveStreamFailedTraceSafely(streamContext, request, exception);
        }

        // Python error 已经转发时，不重复发送 Java error。
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

        // 允许前端先消费 error，再正常结束传输并取消 Python 下游。
        sender.complete();
    }

    /**
     * 使用独立事务保存失败 Trace，不覆盖原始异常。
     */
    private void saveStreamFailedTraceSafely(
            ChatStreamContext streamContext,
            ChatRequest request,
            Throwable exception
    ) {
        try {
            chatPersistenceService.saveFailedTrace(
                    streamContext, request, exception
            );
        } catch (Exception traceException) {
            log.error(
                    "保存流式失败 Trace 异常, traceId={}",
                    streamContext.getTraceId(),
                    traceException
            );
        }
    }

    /**
     * 获取适合通过 SSE 返回的简短错误信息。
     */
    private String safeErrorMessage(Throwable exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) {
            return "流式聊天处理失败";
        }
        return limitText(message, 500);
    }

    /**
     * 标记 Python error 是否已经转发给前端。
     */
    private static final class PythonStreamException extends RuntimeException {

        private final boolean errorForwarded;

        private PythonStreamException(String message, boolean errorForwarded) {
            super(message);
            this.errorForwarded = errorForwarded;
        }

        private boolean isErrorForwarded() {
            return errorForwarded;
        }
    }

    @Override
    public PageResult<ChatConversation> pageConversations(ChatConversationQueryRequest request) {
        // 读取当前租户，只返回当前租户自己的会话。
        Long tenantId = currentUserProvider.requireTenantId();
        Long userId =
                currentUserProvider.requireUserId();
        ChatConversationQueryRequest pageRequest = request == null
                ? new ChatConversationQueryRequest()
                : request;
        long pageNo = pageRequest.normalizedPageNo();
        long pageSize = pageRequest.normalizedPageSize();

        LambdaQueryWrapper<ChatConversation> wrapper = new LambdaQueryWrapper<ChatConversation>()
                .eq(ChatConversation::getTenantId, tenantId)
                .eq(
                        ChatConversation::getUserId,
                        userId
                )
                .orderByDesc(ChatConversation::getUpdatedAt);

        if (request != null && request.getKnowledgeBaseId() != null) {
            // 按知识库过滤会话，便于后续知识库详情页展示相关对话。
            wrapper.eq(ChatConversation::getKnowledgeBaseId, request.getKnowledgeBaseId());
        }
        if (request != null && StringUtils.hasText(request.getKeyword())) {
            // 按标题模糊查询历史会话。
            wrapper.like(ChatConversation::getTitle, request.getKeyword());
        }

        Page<ChatConversation> page = conversationMapper.selectPage(new Page<>(pageNo, pageSize), wrapper);
        return PageResult.from(page);
    }

    @Override
    public ChatConversation getConversation(Long conversationId) {
        // 查询并校验会话属于当前租户。
        return requireCurrentTenantConversation(conversationId);
    }

    @Override
    public List<ChatMessage> listMessages(Long conversationId) {
        // 查询会话前先校验租户权限，避免跨租户读取消息。
        requireCurrentTenantConversation(conversationId);

        // 查询该会话下全部未删除消息，按真实对话顺序返回。
        return messageMapper.selectList(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getConversationId, conversationId)
                .eq(ChatMessage::getDeleted, false)
                .orderByAsc(ChatMessage::getCreatedAt));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteConversation(Long conversationId) {
        // 删除前先校验会话存在且属于当前租户。
        ChatConversation conversation = requireCurrentTenantConversation(conversationId);

        // 逻辑删除会话下的消息，避免删除会话后仍能查到孤立消息。
        messageMapper.delete(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getConversationId, conversation.getId()));

        // 逻辑删除会话本身。
        conversationMapper.deleteById(conversation.getId());
    }
    /**
     * 保存失败 Trace。
     *
     * <p>该方法不能覆盖原始业务异常。即使 Trace 保存失败，
     * 最终仍然应该抛出 Python 调用的原始异常。</p>
     */
    private void saveFailedTraceSafely(
            Long traceId,
            Long tenantId,
            String requestId,
            Long conversationId,
            ChatRequest request,
            Exception originalException
    ) {
        try {
            // HashMap 允许 value 为 null，
            // Map.of 不允许 knowledgeBaseId 等字段为 null。
            Map<String, Object> input = new HashMap<>();

            input.put(
                    "conversationId",
                    conversationId
            );
            input.put(
                    "knowledgeBaseId",
                    request.getKnowledgeBaseId()
            );
            input.put(
                    "question",
                    limitText(request.getQuestion(), 1000)
            );

            ragTraceService.saveFailedTrace(
                    traceId,
                    tenantId,
                    requestId,
                    input,
                    originalException
            );
        } catch (Exception traceException) {
            // Trace 保存失败不能覆盖原始异常。
            log.error(
                    "保存失败 RAG Trace 异常, traceId={}",
                    traceId,
                    traceException
            );
        }
    }
    /**
     * 限制写入 Trace 的文本长度。
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
    /**
     * 校验 Python 没有返回错误的 Trace ID。
     */
    private void validatePythonTraceId(
            Long expectedTraceId,
            PythonChatData pythonData
    ) {
        if (pythonData == null) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python Chat 服务未返回数据"
            );
        }

        if (pythonData.getTraceId() == null) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python Chat 服务未返回 Trace ID"
            );
        }

        if (!expectedTraceId.equals(
                pythonData.getTraceId()
        )) {
            throw new RemoteException(
                    BaseErrorCode.REMOTE_ERROR,
                    "Python Chat 服务返回的 Trace ID 不一致"
            );
        }
    }

    private ChatConversation getOrCreateConversation(ChatRequest request, Long tenantId, Long userId) {
        if (request.getConversationId() != null) {
            ChatConversation conversation = conversationMapper.selectById(request.getConversationId());
            validateTenantConversation(conversation, tenantId,userId);
            return conversation;
        }

        ChatConversation conversation = ChatConversation.builder()
                .id(idGenerator.nextId())
                .tenantId(tenantId)
                .userId(userId)
                .knowledgeBaseId(request.getKnowledgeBaseId())
                .title(buildTitle(request.getQuestion()))
                .channel("WEB")
                .metadata("{}")
                .build();

        conversationMapper.insert(conversation);
        return conversation;
    }

    private ChatMessage saveUserMessage(Long conversationId, Long tenantId, String question) {
        ChatMessage message = ChatMessage.builder()
                .id(idGenerator.nextId())
                .tenantId(tenantId)
                .conversationId(conversationId)
                .role("USER")
                .content(question)
                .citations("[]")
                .tokenUsage("{}")
                .build();

        messageMapper.insert(message);
        return message;
    }

    private ChatMessage saveAssistantMessage(Long conversationId,
                                             Long tenantId,
                                             Long parentMessageId,
                                             String answer,
                                             String citations,
                                             String tokenUsage,
                                             Long traceId) {
        ChatMessage message = ChatMessage.builder()
                .id(idGenerator.nextId())
                .tenantId(tenantId)
                .conversationId(conversationId)
                .parentMessageId(parentMessageId)
                .role("ASSISTANT")
                .content(answer)
                .citations(citations)
                .tokenUsage(tokenUsage)
                .traceId(traceId)
                .build();

        messageMapper.insert(message);
        return message;
    }

    private List<ChatMessage> listRecentMessages(Long conversationId) {
        // 1. 优先读 Redis 工作记忆（命中即返回，省 PG 查询）。
        List<ChatMessage> cached = memoryCache.getRecentMessages(
                conversationId, HISTORY_LIMIT
        );
        if (!cached.isEmpty()) {
            return cached;
        }

        // 2. 未命中：先倒序查询最近 N 条消息。
        // 先倒序查询最近 N 条消息，控制传给模型的上下文长度。
        List<ChatMessage> messages = messageMapper.selectList(new LambdaQueryWrapper<ChatMessage>()
                .eq(ChatMessage::getConversationId, conversationId)
                .eq(ChatMessage::getDeleted, false)
                .orderByDesc(ChatMessage::getCreatedAt)
                        .orderByDesc(ChatMessage::getId)
                .last("LIMIT " + HISTORY_LIMIT));

        // 3. 按时间正序返回，并回填 Redis（从旧到新，leftPush 后最新在前）。
        List<ChatMessage> ordered = messages.stream()
                .sorted(Comparator.comparing(ChatMessage::getCreatedAt))
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

    private ChatConversation requireCurrentTenantConversation(Long conversationId) {
        if (conversationId == null) {
            throw new ClientException(BaseErrorCode.BAD_REQUEST, "会话 ID 不能为空");
        }
        ChatConversation conversation = conversationMapper.selectById(conversationId);
        validateTenantConversation(conversation, currentUserProvider.requireTenantId(), currentUserProvider.requireUserId());
        return conversation;
    }

    private void validateTenantConversation(ChatConversation conversation, Long tenantId,Long userId) {
        if (conversation == null || Boolean.TRUE.equals(conversation.getDeleted())) {
            throw new ClientException(BaseErrorCode.NOT_FOUND, "会话不存在");
        }
        if (!tenantId.equals(conversation.getTenantId())) {
            throw new ClientException(BaseErrorCode.FORBIDDEN, "无权访问该会话");
        }
        if (!userId.equals(conversation.getUserId())) {       // ← 也检查了 userId
            throw new ClientException(BaseErrorCode.FORBIDDEN, "无权访问其他用户的会话");
        }

    }

    private String buildTitle(String question) {
        String text = question.trim();
        if (text.length() <= 30) {
            return text;
        }
        return text.substring(0, 30);
    }

    private void validateRequest(ChatRequest request) {
        if (request == null || !StringUtils.hasText(request.getQuestion())) {
            throw new ClientException(BaseErrorCode.BAD_REQUEST, "问题不能为空");
        }
    }



}
