package com.example.rag.evaluation.controller;

import com.example.rag.common.api.ApiResult;
import com.example.rag.evaluation.dto.RetrievalConfigResponse;
import com.example.rag.evaluation.dto.RetrievalDebugRequest;
import com.example.rag.evaluation.dto.RetrievalDebugResponse;
import com.example.rag.evaluation.service.RetrievalDebugService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 检索调试接口。
 *
 * <p>该接口会展示原始知识库分片和检索得分，
 * 因此只允许平台管理员和租户管理员访问。</p>
 */
@RestController
@RequestMapping("/api/retrieval")
@RequiredArgsConstructor
@PreAuthorize(
        "hasAnyRole('PLATFORM_ADMIN', 'ADMIN')"
)
public class RetrievalDebugController {

    /** 检索调试业务服务。 */
    private final RetrievalDebugService retrievalDebugService;

    /**
     * 执行完整检索调试。
     *
     * @param request 检索参数
     * @return 各阶段结果、上下文和耗时
     */
    @PostMapping("/debug")
    public ApiResult<RetrievalDebugResponse> debug(
            @Valid
            @RequestBody
            RetrievalDebugRequest request
    ) {
        // Controller 只负责接收请求和返回统一响应。
        RetrievalDebugResponse response =
                retrievalDebugService.debug(request);

        return ApiResult.ok(response);
    }

    /**
     * 获取检索调试默认参数。
     */
    @GetMapping("/config")
    public ApiResult<RetrievalConfigResponse> getConfig() {
        return ApiResult.ok(
                retrievalDebugService.getConfig()
        );
    }
}
