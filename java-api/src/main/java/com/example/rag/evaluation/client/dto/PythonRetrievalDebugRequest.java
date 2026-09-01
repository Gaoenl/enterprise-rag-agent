package com.example.rag.evaluation.client.dto;

import com.example.rag.evaluation.dto.RetrievalMode;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Java 调用 Python 检索调试接口的内部请求。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PythonRetrievalDebugRequest {

    /** Java 与 Python 日志关联 ID。 */
    private String requestId;

    /** 从 JWT 获取的当前租户 ID。 */
    private Long tenantId;

    /** 从 JWT 获取的当前用户 ID。 */
    private Long userId;

    /** Java 已经完成权限校验的知识库 ID。 */
    private Long knowledgeBaseId;

    /** 用户输入的原始问题。 */
    private String question;

    /** VECTOR、KEYWORD 或 HYBRID。 */
    private RetrievalMode mode;

    /** 是否执行查询改写。 */
    private Boolean enableRewrite;

    /** 是否执行 Rerank。 */
    private Boolean enableRerank;

    /** 向量召回数量。 */
    private Integer vectorTopK;

    /** 关键词召回数量。 */
    private Integer keywordTopK;

    /** 融合后保留数量。 */
    private Integer fusionTopK;

    /** 最终保留数量。 */
    private Integer finalTopK;

    /** RRF 平滑参数。 */
    private Integer rrfK;

    /** 向量召回结果在 Weighted RRF 中的权重。 */
    private Double vectorWeight;

    /** 关键词召回结果在 Weighted RRF 中的权重。 */
    private Double keywordWeight;
}
