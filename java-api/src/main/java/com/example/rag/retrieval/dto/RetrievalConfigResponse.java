package com.example.rag.retrieval.dto;

import lombok.Data;

/**
 * 检索调试默认参数（转发自 Python 服务端配置）。
 */
@Data
public class RetrievalConfigResponse {

    private Integer vectorTopK;
    private Integer keywordTopK;
    private Integer fusionTopK;
    private Integer finalTopK;
    private Integer rrfK;
    private Double vectorWeight;
    private Double keywordWeight;
    private Boolean multiQueryEnabled;
    private Integer multiQueryTopK;
    private Boolean synonymExpansionEnabled;
}
