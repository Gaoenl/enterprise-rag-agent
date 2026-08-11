package com.example.rag.knowledge.dto;

import lombok.Data;

/**
 * 更新知识库请求。
 */
@Data
public class KnowledgeBaseUpdateRequest {

    /**
     * 知识库 ID。
     */
    private Long id;
    /**
     * 知识库名称。
     */
    private String name;
    /**
     * 知识库描述。
     */
    private String description;
    /**
     * 可见性，例如 PRIVATE、TENANT。
     */
    private String visibility;
    /**
     * 业务域编码，默认 GENERAL。
     */
    private String domainCode;
    /**
     * 入库流水线配置（切分策略 + 向量化参数）。可选，不传不更新。
     */
    private com.example.rag.ingestion.config.PipelineConfig pipelineConfig;

}
