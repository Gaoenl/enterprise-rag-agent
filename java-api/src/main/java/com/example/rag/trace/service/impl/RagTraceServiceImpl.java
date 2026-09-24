package com.example.rag.trace.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.rag.common.api.PageResult;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.security.CurrentUserProvider;
import com.example.rag.trace.dto.RagTraceListItem;
import com.example.rag.trace.dto.RagTraceQueryRequest;
import com.example.rag.trace.dto.RagTraceResponse;
import com.example.rag.trace.dto.RagTraceStatisticsResponse;
import com.example.rag.trace.entity.RagTrace;
import com.example.rag.chat.entity.ChatConversation;
import com.example.rag.chat.mapper.ChatConversationMapper;
import com.example.rag.trace.mapper.RagTraceMapper;
import com.example.rag.trace.service.RagTraceService;
import com.example.rag.user.entity.SysUser;
import com.example.rag.user.mapper.SysUserMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
/**
 * RAG Trace 持久化服务实现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RagTraceServiceImpl implements RagTraceService {

    private final RagTraceMapper traceMapper;
    private final ChatConversationMapper conversationMapper;
    private final SysUserMapper userMapper;
    private final ObjectMapper objectMapper;
    private final CurrentUserProvider currentUserProvider;

    @Override
    public RagTraceResponse getTrace(Long traceId) {
        // Trace ID 不能为空。
        if (traceId == null) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "Trace ID 不能为空"
            );
        }

        // 从可信用户上下文中取得租户 ID。
        Long tenantId = currentUserProvider.requireTenantId();

        // 查询时同时加入 tenant_id，避免跨租户读取。
        RagTrace trace = traceMapper.selectOne(
                new LambdaQueryWrapper<RagTrace>()
                        .eq(RagTrace::getId, traceId)
                        .eq(RagTrace::getTenantId, tenantId)
                        .last("LIMIT 1")
        );

        if (trace == null) {
            throw new ClientException(
                    BaseErrorCode.NOT_FOUND,
                    "RAG Trace 不存在"
            );
        }

        return toResponse(trace);
    }

    @Override
    public List<RagTraceResponse> listConversationTraces(
            Long conversationId
    ) {
        if (conversationId == null) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "会话 ID 不能为空"
            );
        }

        Long tenantId = currentUserProvider.requireTenantId();

        // 按创建时间升序返回一次会话中的 Trace。
        return traceMapper.selectList(
                        new LambdaQueryWrapper<RagTrace>()
                                .eq(
                                        RagTrace::getTenantId,
                                        tenantId
                                )
                                .eq(
                                        RagTrace::getConversationId,
                                        conversationId
                                )
                                .orderByAsc(
                                        RagTrace::getCreatedAt
                                )
                )
                .stream()
                .map(this::toResponse)
                .toList();
    }

    /**
     * 将 Trace 实体转换为接口响应。
     */
    private RagTraceResponse toResponse(RagTrace trace) {
        return RagTraceResponse.builder()
                .id(trace.getId())
                .tenantId(trace.getTenantId())
                .conversationId(trace.getConversationId())
                .messageId(trace.getMessageId())
                .traceType(trace.getTraceType())
                .requestId(trace.getRequestId())
                .input(readJson(trace.getInput(), false))
                .output(readJson(trace.getOutput(), false))
                .nodes(readJson(trace.getNodes(), true))
                .tokenUsage(readJson(trace.getTokenUsage(), false))
                .degradedReasons(readJson(trace.getDegradedReasons(), true))
                .startedAt(trace.getStartedAt())
                .finishedAt(trace.getFinishedAt())
                .latencyMs(trace.getLatencyMs())
                .status(trace.getStatus())
                .errorMessage(trace.getErrorMessage())
                .createdAt(trace.getCreatedAt())
                .updatedAt(trace.getUpdatedAt())
                .build();
    }

    /**
     * 将数据库中的 JSONB 字符串解析为 JsonNode。
     */
    private JsonNode readJson(
            String json,
            boolean arrayDefault
    ) {
        if (!StringUtils.hasText(json)) {
            return arrayDefault
                    ? objectMapper.createArrayNode()
                    : objectMapper.createObjectNode();
        }

        try {
            return objectMapper.readTree(json);
        } catch (JsonProcessingException exception) {
            log.error(
                    "解析 Trace JSON 失败, json={}",
                    limitText(json, 500),
                    exception
            );

            return arrayDefault
                    ? objectMapper.createArrayNode()
                    : objectMapper.createObjectNode();
        }
    }

    // ──────────────────────────────────────────────
    // 分页列表 + 统计
    // ──────────────────────────────────────────────

    @Override
    public PageResult<RagTraceListItem> pageTraces(RagTraceQueryRequest request) {
        Long tenantId = currentUserProvider.requireTenantId();
        Long pageNo = request.getPageNo() == null || request.getPageNo() < 1 ? 1L : request.getPageNo();
        Long pageSize = request.getPageSize() == null || request.getPageSize() < 1
                ? 20L : Math.min(request.getPageSize(), 100L);

        LambdaQueryWrapper<RagTrace> wrapper = new LambdaQueryWrapper<RagTrace>()
                .eq(RagTrace::getTenantId, tenantId)
                .orderByDesc(RagTrace::getCreatedAt);

        if (StringUtils.hasText(request.getStatus())) {
            wrapper.eq(RagTrace::getStatus, request.getStatus().toUpperCase());
        }
        if (request.getConversationId() != null) {
            wrapper.eq(RagTrace::getConversationId, request.getConversationId());
        }
        if (StringUtils.hasText(request.getKeyword())) {
            wrapper.and(w -> w
                    .like(RagTrace::getRequestId, request.getKeyword())
                    .or()
                    .like(RagTrace::getInput, request.getKeyword()));
        }

        Page<RagTrace> page = traceMapper.selectPage(new Page<>(pageNo, pageSize), wrapper);

        List<RagTraceListItem> items = page.getRecords().stream()
                .map(trace -> RagTraceListItem.builder()
                        .id(trace.getId())
                        .conversationId(trace.getConversationId())
                        .status(trace.getStatus())
                        .latencyMs(trace.getLatencyMs())
                        .question(extractQuestion(trace.getInput()))
                        .intent(extractIntent(trace.getOutput()))
                        .degraded("DEGRADED".equals(trace.getStatus()))
                        .createdAt(trace.getCreatedAt())
                        .build())
                .toList();

        // 批量填充用户名
        fillUsernames(items);

        return PageResult.of(items, page.getTotal(), page.getCurrent(), page.getSize());
    }

    @Override
    public RagTraceStatisticsResponse statistics() {
        Long tenantId = currentUserProvider.requireTenantId();
        List<RagTrace> all = traceMapper.selectList(
                new LambdaQueryWrapper<RagTrace>()
                        .eq(RagTrace::getTenantId, tenantId));

        long total = all.size();
        long success = all.stream().filter(t -> "SUCCESS".equals(t.getStatus())).count();
        long failed = all.stream().filter(t -> "FAILED".equals(t.getStatus())).count();
        long degraded = all.stream().filter(t -> "DEGRADED".equals(t.getStatus())).count();

        double avgLatency = all.stream()
                .filter(t -> t.getLatencyMs() != null)
                .mapToLong(RagTrace::getLatencyMs)
                .average().orElse(0);

        Instant todayStart = Instant.now().truncatedTo(ChronoUnit.DAYS);
        long todayCount = all.stream()
                .filter(t -> t.getCreatedAt() != null && !t.getCreatedAt().isBefore(todayStart))
                .count();

        return RagTraceStatisticsResponse.builder()
                .totalCount(total)
                .successCount(success)
                .failedCount(failed)
                .degradedCount(degraded)
                .successRate(total > 0 ? (double) success / total : 0)
                .avgLatencyMs((long) avgLatency)
                .todayCount(todayCount)
                .build();
    }

    /**
     * 批量填充列表中每条 trace 的 userId 和 username。
     */
    private void fillUsernames(List<RagTraceListItem> items) {
        // 收集所有有效的 conversationId
        List<Long> conversationIds = items.stream()
                .map(RagTraceListItem::getConversationId)
                .filter(id -> id != null)
                .distinct()
                .toList();

        if (conversationIds.isEmpty()) return;

        // 批量查询会话 → userId 映射
        List<ChatConversation> conversations = conversationMapper.selectBatchIds(conversationIds);
        Map<Long, Long> convUserMap = conversations.stream()
                .collect(Collectors.toMap(ChatConversation::getId, ChatConversation::getUserId, (a, b) -> a));

        // 收集所有 userId
        List<Long> userIds = convUserMap.values().stream().distinct().toList();
        if (userIds.isEmpty()) return;

        // 批量查询用户 → username 映射
        List<SysUser> users = userMapper.selectBatchIds(userIds);
        Map<Long, String> userMap = users.stream()
                .collect(Collectors.toMap(SysUser::getId, SysUser::getUsername, (a, b) -> a));

        // 回填
        for (RagTraceListItem item : items) {
            Long userId = convUserMap.get(item.getConversationId());
            if (userId != null) {
                item.setUserId(userId);
                item.setUsername(userMap.get(userId));
            }
        }
    }

    private String extractQuestion(String inputJson) {
        if (inputJson == null) return null;
        try {
            JsonNode node = objectMapper.readTree(inputJson);
            String q = node.path("question").asText(null);
            return q != null && q.length() > 80 ? q.substring(0, 80) + "..." : q;
        } catch (Exception e) {
            return null;
        }
    }

    private String extractIntent(String outputJson) {
        if (outputJson == null) return null;
        try {
            return objectMapper.readTree(outputJson).path("intent").asText(null);
        } catch (Exception e) {
            return null;
        }
    }

    private String limitText(String text, int maxLength) {
        if (text == null || text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength);
    }

}
