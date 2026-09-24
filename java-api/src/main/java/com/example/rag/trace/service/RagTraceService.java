package com.example.rag.trace.service;

import com.example.rag.common.api.PageResult;
import com.example.rag.trace.dto.RagTraceListItem;
import com.example.rag.trace.dto.RagTraceQueryRequest;
import com.example.rag.trace.dto.RagTraceResponse;
import com.example.rag.trace.dto.RagTraceStatisticsResponse;

import java.util.List;

/**
 * RAG Trace 持久化服务。
 */
public interface RagTraceService {

    /**
     * 根据 Trace ID 查询当前租户的 Trace。
     *
     * @param traceId Trace ID
     * @return Trace 查询响应
     */
    RagTraceResponse getTrace(Long traceId);

    /**
     * 查询指定会话下的 Trace。
     *
     * @param conversationId 会话 ID
     * @return Trace 列表
     */
    List<RagTraceResponse> listConversationTraces(Long conversationId);

    /**
     * 分页查询 Trace 列表，支持按状态、关键词、会话筛选。
     */
    PageResult<RagTraceListItem> pageTraces(RagTraceQueryRequest request);

    /**
     * Trace 统计数据（总数、成功率、平均延迟、今日调用次数）。
     */
    RagTraceStatisticsResponse statistics();
}
