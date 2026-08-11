package com.example.rag.knowledge.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.example.rag.common.config.database.JsonbTypeHandler;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 知识库实体，对应数据库表 {@code kb_knowledge_base}。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
@TableName(value = "kb_knowledge_base", autoResultMap = true)
public class KnowledgeBase {

    /**
     * 知识库主键 ID。
     */
    @TableId
    private Long id;
    /**
     * 所属租户 ID。
     */
    private Long tenantId;
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
     * 业务域编码：EXPENSE / HR / CONTRACT / POLICY / GENERAL。
     * 用于意图 L1 路由时按域过滤知识库。
     */
    private String domainCode;
    /**
     * 默认 embedding 模型配置 ID。
     */
    private Long embeddingModelConfigId;
    /**
     * 流水线配置（切分策略 + 向量化参数）。
     */
    @TableField(value = "chunk_strategy", typeHandler = com.example.rag.common.config.database.PipelineConfigTypeHandler.class)
    private com.example.rag.ingestion.config.PipelineConfig chunkStrategy;
    /**
     * 知识库状态，默认 1 表示启用。
     */
    private Integer status;
    /**
     * 知识库中未逻辑删除的文档数量。
     * 只允许通过 Mapper 的原子 SQL 更新，防止通用 updateById 覆盖并发计数。
     */
    @TableField(updateStrategy = FieldStrategy.NEVER)
    private Long documentCount;
    /**
     * 创建人用户 ID。
     */
    private Long createdBy;
    /**
     * 创建时间。
     */
    @TableField(fill = FieldFill.INSERT)
    private Instant createdAt;
    /**
     * 更新时间。
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
    /**
     * 软删除标记。
     */
    @TableField(value = "deleted", fill = FieldFill.INSERT)
    @TableLogic(value = "false", delval = "true")
    private Boolean deleted;
}
