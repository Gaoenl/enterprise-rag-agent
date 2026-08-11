package com.example.rag.retrieval.service;

import com.example.rag.retrieval.dto.RetrievalDebugRequest;
import com.example.rag.retrieval.dto.RetrievalDebugResponse;
import com.example.rag.retrieval.dto.RetrievalConfigResponse;

/**
 * 检索调试业务服务。
 */
public interface RetrievalDebugService {

    /**
     * 校验知识库权限并执行检索调试。
     *
     * @param request 前端调试参数
     * @return 各检索阶段的结果
     */
    RetrievalDebugResponse debug(
            RetrievalDebugRequest request
    );

    /**
     * 获取检索调试默认参数。
     *
     * @return 检索参数配置
     */
    RetrievalConfigResponse getConfig();
}
