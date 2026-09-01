package com.example.rag.evaluation.dto;

import lombok.Data;

/**
 * 检索调试各阶段耗时，单位为毫秒。
 */
@Data
public class RetrievalTimingResponse {

    /** Query Rewrite 耗时。 */
    private Long rewriteMillis;

    /** 向量检索耗时。 */
    private Long vectorMillis;

    /** 关键词检索耗时。 */
    private Long keywordMillis;

    /** RRF 融合耗时。 */
    private Long fusionMillis;

    /** Rerank 耗时。 */
    private Long rerankMillis;

    /** 上下文打包耗时。 */
    private Long packingMillis;

    /** 完整检索流程总耗时。 */
    private Long totalMillis;
}