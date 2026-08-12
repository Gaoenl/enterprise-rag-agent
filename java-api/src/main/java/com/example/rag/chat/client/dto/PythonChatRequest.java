package com.example.rag.chat.client.dto;

import lombok.Data;

import java.util.List;

/**
 * 调用 Python Chat 接口的请求体。
 */
@Data
public class PythonChatRequest {
    /**
     * 用户当前输入的问题。
     */
    private String question;

    /**
     * 本次调用指定的模型。
     */
    private String model;

    /**
     * 当前登录用户所属租户 ID。
     */
    private Long tenantId;

    /**
     * 当前登录用户 ID。
     */
    private Long userId;
    /**
     * 本次 RAG 请求的 Trace ID，由 Java 生成。
     */
    private Long traceId;

    /**
     * Java 与 Python 日志之间的请求关联 ID。
     */
    private String requestId;

    /**
     * 当前会话 ID。
     */
    private Long conversationId;

    /**
     * 用户在前端明确选择的知识库 ID。
     */
    private Long knowledgeBaseId;
    /** 会话摘要（Java 侧压缩后），可空。 */
    private String summary;
    /**
     * Java 数据库中查询出的最近会话历史。
     */
    private List<PythonChatHistoryMessage> history;
}