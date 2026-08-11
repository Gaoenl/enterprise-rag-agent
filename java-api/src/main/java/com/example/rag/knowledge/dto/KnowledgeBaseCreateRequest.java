package com.example.rag.knowledge.dto;

import com.example.rag.ingestion.config.PipelineConfig;
import lombok.Data;

/**
 * 创建知识库请求。
 */
@Data
public class KnowledgeBaseCreateRequest {

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
     * 入库流水线配置（切分策略 + 向量化参数）。可选，不传使用默认值。
     */
    private PipelineConfig pipelineConfig;

}
