package com.example.rag.chat.dto;

import com.example.rag.chat.client.dto.PythonChatRequest;
import lombok.Builder;
import lombok.Getter;

/**
 * Java 流式聊天过程中的内部上下文。
 *
 * <p>该对象不作为接口响应，只负责在准备事务、
 * Python SSE 调用和完成事务之间传递数据。</p>
 */
@Getter
@Builder
public class ChatStreamContext {

    /** 当前租户 ID。 */
    private Long tenantId;

    /** 当前登录用户 ID。 */
    private Long userId;

    /** 当前会话 ID。 */
    private Long conversationId;

    /** 本轮 RAG Trace ID。 */
    private Long traceId;

    /** Java 和 Python 日志关联 ID。 */
    private String requestId;

    /** 发送给 Python 的完整请求。 */
    private PythonChatRequest pythonRequest;
}
