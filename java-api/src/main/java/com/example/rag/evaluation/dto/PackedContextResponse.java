package com.example.rag.evaluation.dto;

import lombok.Data;

import java.util.List;

/**
 * 最终上下文打包结果。
 */
@Data
public class PackedContextResponse {

    /** 最终准备发送给 LLM 的上下文文本。 */
    private String text;

    /** 上下文总字符数。 */
    private Integer totalChars;

    /** 是否因为字符预算发生截断。 */
    private Boolean truncated;

    /** 实际进入上下文的分片。 */
    private List<RetrievalCandidateResponse> documents;
}