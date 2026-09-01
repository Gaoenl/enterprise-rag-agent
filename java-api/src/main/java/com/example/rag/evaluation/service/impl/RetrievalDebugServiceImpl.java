package com.example.rag.evaluation.service.impl;

import com.example.rag.common.context.RequestContext;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.security.CurrentUserProvider;
import com.example.rag.knowledge.service.KnowledgeBaseService;
import com.example.rag.evaluation.client.PythonRetrievalDebugClient;
import com.example.rag.evaluation.client.dto.PythonRetrievalDebugRequest;
import com.example.rag.evaluation.dto.RetrievalDebugRequest;
import com.example.rag.evaluation.dto.RetrievalDebugResponse;
import com.example.rag.evaluation.dto.RetrievalConfigResponse;
import com.example.rag.evaluation.dto.RetrievalMode;
import com.example.rag.evaluation.service.RetrievalDebugService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.UUID;

/**
 * 检索调试业务服务实现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RetrievalDebugServiceImpl
        implements RetrievalDebugService {

    /** Python 检索调试客户端。 */
    private final PythonRetrievalDebugClient pythonClient;

    /** 当前登录用户信息提供器。 */
    private final CurrentUserProvider currentUserProvider;

    /** 知识库业务服务。 */
    private final KnowledgeBaseService knowledgeBaseService;

    /**
     * 执行检索调试。
     */
    @Override
    public RetrievalDebugResponse debug(
            RetrievalDebugRequest request
    ) {
        // Service 层再次校验关键参数，
        // 避免该方法从非 Controller 场景调用时绕过校验。
        validateRequest(request);

        // tenantId 必须来自 JWT，不能使用浏览器参数。
        Long tenantId =
                currentUserProvider.requireTenantId();

        // userId 必须来自 JWT，用于审计和日志关联。
        Long userId =
                currentUserProvider.requireUserId();

        // 指定知识库时才校验其存在、属于当前租户且处于启用状态；
        // 未指定时由 Python 在当前租户全部知识库范围内检索。
        if (request.getKnowledgeBaseId() != null) {
            knowledgeBaseService.ensureUsable(
                    request.getKnowledgeBaseId()
            );
        }

        // 优先使用过滤器生成的 requestId。
        String requestId = resolveRequestId();

        // 构造只在 Java 与 Python 之间传递的可信请求。
        PythonRetrievalDebugRequest pythonRequest =
                PythonRetrievalDebugRequest.builder()
                        .requestId(requestId)
                        .tenantId(tenantId)
                        .userId(userId)
                        .knowledgeBaseId(
                                request.getKnowledgeBaseId()
                        )
                        .question(
                                request.getQuestion().trim()
                        )
                        .mode(defaultMode(request.getMode()))
                        .enableRewrite(
                                defaultTrue(
                                        request.getEnableRewrite()
                                )
                        )
                        .enableRerank(
                                defaultTrue(
                                        request.getEnableRerank()
                                )
                        )
                        .vectorTopK(request.getVectorTopK())
                        .keywordTopK(request.getKeywordTopK())
                        .fusionTopK(request.getFusionTopK())
                        .finalTopK(request.getFinalTopK())
                        .rrfK(request.getRrfK())
                        .vectorWeight(request.getVectorWeight())
                        .keywordWeight(request.getKeywordWeight())
                        .build();

        log.info(
                "开始执行检索调试, requestId={}, "
                        + "tenantId={}, userId={}, "
                        + "knowledgeBaseId={}, mode={}",
                requestId,
                tenantId,
                userId,
                request.getKnowledgeBaseId(),
                pythonRequest.getMode()
        );

        // 调用 Python 执行真正的检索编排。
        RetrievalDebugResponse response =
                pythonClient.debug(pythonRequest);

        // 日志只记录数量和耗时，不记录问题及分片正文。
        log.info(
                "检索调试完成, requestId={}, "
                        + "knowledgeBaseId={}, "
                        + "vectorCount={}, keywordCount={}, "
                        + "fusionCount={}, rerankCount={}, "
                        + "totalMillis={}, degraded={}",
                requestId,
                request.getKnowledgeBaseId(),
                sizeOf(response.getVectorResults()),
                sizeOf(response.getKeywordResults()),
                sizeOf(response.getFusionResults()),
                sizeOf(response.getRerankResults()),
                response.getTimings() == null
                        ? null
                        : response
                        .getTimings()
                        .getTotalMillis(),
                response.getDegraded()
        );

        return response;
    }

    @Override
    public RetrievalConfigResponse getConfig() {
        // 检索参数以 Python 服务端配置为唯一真相，Java 直接转发。
        return pythonClient.getConfig();
    }

    /**
     * 校验检索调试请求。
     */
    private void validateRequest(
            RetrievalDebugRequest request
    ) {
        if (request == null) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "检索调试请求不能为空"
            );
        }

        if (!StringUtils.hasText(request.getQuestion())) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "检索问题不能为空"
            );
        }

        if (request.getQuestion().trim().length() > 4000) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "检索问题不能超过 4000 个字符"
            );
        }

        // Weighted RRF 可以关闭一路召回，但混合检索不能同时关闭两路。
        if (defaultMode(request.getMode()) == RetrievalMode.HYBRID
                && Double.compare(defaultWeight(request.getVectorWeight()), 0D) == 0
                && Double.compare(defaultWeight(request.getKeywordWeight()), 0D) == 0) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "向量权重和关键词权重不能同时为 0"
            );
        }
    }

    /** 未显式传入权重时按默认权重 1 参与校验。 */
    private double defaultWeight(Double weight) {
        return weight == null ? 1D : weight;
    }

    /**
     * 获取当前请求链路 ID。
     */
    private String resolveRequestId() {
        String requestId = RequestContext.requestId();

        // 单元测试或非 Web 调用可能没有经过 Filter。
        return StringUtils.hasText(requestId)
                ? requestId
                : UUID.randomUUID().toString();
    }

    /**
     * 请求未指定模式时默认使用混合检索。
     */
    private RetrievalMode defaultMode(
            RetrievalMode mode
    ) {
        return mode == null
                ? RetrievalMode.HYBRID
                : mode;
    }

    /**
     * 布尔配置未传入时默认开启。
     */
    private Boolean defaultTrue(Boolean value) {
        return value == null || value;
    }

    /**
     * 安全获取列表长度。
     */
    private int sizeOf(java.util.List<?> values) {
        return values == null ? 0 : values.size();
    }
}
