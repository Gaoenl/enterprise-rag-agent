package com.example.rag.chat.client.dto;

import lombok.Data;

/**
 * 调用 Python Chat 接口的请求体。
 */
@Data
public class PythonChatRequest {
    private String question;
    private Long conversationId;
    private Long knowledgeBaseId;

    private Long tenantId;
    private Long userId;

    private Long traceId;
    private String requestId;
    private String model;
}
