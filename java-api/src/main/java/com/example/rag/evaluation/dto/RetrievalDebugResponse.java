package com.example.rag.evaluation.dto;

import lombok.Data;

import java.util.List;

/**
 * 检索调试完整响应。
 */
@Data
public class RetrievalDebugResponse {

    /** 用户输入的原始问题。 */
    private String originalQuery;

    /** 用于向量检索的语义查询。 */
    private String semanticQuery;

    /** 用于关键词检索的关键词。 */
    private List<String> keywords;

    /** 多查询召回实际使用的子查询列表。 */
    private List<String> alternativeQueries;

    /** 多路向量候选合并去重后的数量。 */
    private Integer vectorMergedCount;

    /** 实际执行的检索模式。 */
    private RetrievalMode mode;

    /** 是否执行了查询改写。 */
    private Boolean rewriteApplied;

    /** 是否成功执行了 Rerank。 */
    private Boolean rerankApplied;

    /** 检索链路是否发生降级。 */
    private Boolean degraded;

    /** 向量检索结果。 */
    private List<RetrievalCandidateResponse> vectorResults;

    /** 关键词检索结果。 */
    private List<RetrievalCandidateResponse> keywordResults;

    /** RRF 融合结果。 */
    private List<RetrievalCandidateResponse> fusionResults;

    /** Rerank 或降级后的最终候选。 */
    private List<RetrievalCandidateResponse> rerankResults;

    /** 最终上下文打包结果。 */
    private PackedContextResponse packedContext;

    /** 各阶段耗时。 */
    private RetrievalTimingResponse timings;

    /** 降级、配置关闭等非致命警告。 */
    private List<String> warnings;
}
