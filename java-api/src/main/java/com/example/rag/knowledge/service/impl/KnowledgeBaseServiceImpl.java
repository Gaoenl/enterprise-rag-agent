package com.example.rag.knowledge.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.rag.chat.dto.ChatKnowledgeBaseOption;
import com.example.rag.common.api.PageResult;
import com.example.rag.common.context.UserContext;
import com.example.rag.common.error.BaseErrorCode;
import com.example.rag.common.error.BusinessException;
import com.example.rag.common.error.ClientException;
import com.example.rag.common.error.ServiceException;
import com.example.rag.common.id.IdGenerator;
import com.example.rag.common.security.CurrentUserProvider;
import com.example.rag.embedding.config.EmbeddingClientProperties;
import com.example.rag.ingestion.config.PipelineConfig;
import com.example.rag.knowledge.dto.KnowledgeBaseCreateRequest;
import com.example.rag.knowledge.dto.KnowledgeBaseQueryRequest;
import com.example.rag.knowledge.dto.KnowledgeBaseUpdateRequest;
import com.example.rag.knowledge.entity.KnowledgeBase;
import com.example.rag.knowledge.entity.KnowledgeDocument;
import com.example.rag.knowledge.mapper.KnowledgeBaseMapper;
import com.example.rag.knowledge.mapper.KnowledgeDocumentChunkMapper;
import com.example.rag.knowledge.mapper.KnowledgeDocumentMapper;
import com.example.rag.knowledge.service.KnowledgeBaseService;
import com.example.rag.model.entity.ModelConfig;
import com.example.rag.model.mapper.ModelConfigMapper;
import com.example.rag.tenant.service.TenantService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 知识库服务实现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KnowledgeBaseServiceImpl implements KnowledgeBaseService {

    private static final String DEFAULT_VISIBILITY = "PRIVATE";

    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final IdGenerator idGenerator;
    private final KnowledgeDocumentMapper documentMapper;
    private final KnowledgeDocumentChunkMapper chunkMapper;
    private final CurrentUserProvider currentUserProvider;
    private final ObjectMapper objectMapper;

    /**
     * 创建知识库，并绑定当前请求中的租户和创建人。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public KnowledgeBase createKnowledgeBase(KnowledgeBaseCreateRequest request) {
        // 从用户上下文读取当前租户 ID，保证知识库属于当前租户。
        Long tenantId =  currentUserProvider.requireTenantId();
        // 从用户上下文读取当前用户 ID，用于记录创建人。
        Long currentUserId = currentUserProvider.requireUserId();
        validateEmbeddingConfig(request.getPipelineConfig());
        // 构造知识库实体，并补齐默认可见性、切片策略、状态和软删除标记。
        KnowledgeBase knowledgeBase = KnowledgeBase.builder()
                .id(idGenerator.nextId())
                .tenantId(tenantId)
                .name(request.getName())
                .description(request.getDescription())
                .visibility(defaultIfBlank(request.getVisibility(), DEFAULT_VISIBILITY))
                .domainCode(request.getDomainCode())
                .chunkStrategy(request.getPipelineConfig() != null
                        ? request.getPipelineConfig()
                        : PipelineConfig.defaults())
                .status(1)
                .documentCount(0L)
                .createdBy(currentUserId)
                .build();
        // 调用 Mapper 将知识库记录写入数据库。
        knowledgeBaseMapper.insert(knowledgeBase);
        return knowledgeBase;
    }

    /**
     * 查询当前租户下的知识库；不存在时抛出统一业务异常。
     */
    @Override
    public KnowledgeBase getKnowledgeBase(Long knowledgeBaseId) {
        // 按知识库 ID 和当前租户 ID 查询，避免跨租户读取数据。
        KnowledgeBase knowledgeBase = selectCurrentTenantKnowledgeBase(knowledgeBaseId);
        if (knowledgeBase == null) {
            throw new BusinessException(BaseErrorCode.NOT_FOUND, "知识库不存在");
        }
        return knowledgeBase;
    }

    /**
     * 分页查询当前租户下的知识库，支持按名称或描述模糊搜索。
     */
    @Override
    public PageResult<KnowledgeBase> pageKnowledgeBases(KnowledgeBaseQueryRequest request) {
        // 规范化页码，避免传入小于 1 的非法页码。
        long pageNo = request.normalizedPageNo();
        // 规范化分页大小，避免一次查询过多数据。
        long pageSize = request.normalizedPageSize();
        // 从用户上下文读取当前租户 ID，分页查询只返回当前租户的数据。
        Long tenantId = currentUserProvider.requireTenantId();
        // 构造基础查询条件：当前租户 + 按创建时间倒序。
        LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<KnowledgeBase>()
                .eq(KnowledgeBase::getTenantId, tenantId)
                .orderByDesc(KnowledgeBase::getCreatedAt);
        if (!isBlank(request.getKeyword())) {
            // 如果传入关键字，则按知识库名称或描述进行模糊搜索。
            wrapper.and(item -> item
                    .like(KnowledgeBase::getName, request.getKeyword())
                    .or()
                    .like(KnowledgeBase::getDescription, request.getKeyword()));
        }
        // 执行 MyBatis-Plus 分页查询。
        Page<KnowledgeBase> page = knowledgeBaseMapper.selectPage(new Page<>(pageNo, pageSize), wrapper);
        // 将 MyBatis-Plus 分页结果转换成项目统一分页返回结构。
        return PageResult.from(page);
    }

    /**
     * 更新当前租户下的知识库基础信息。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public KnowledgeBase updateKnowledgeBase(KnowledgeBaseUpdateRequest request) {
        // 更新前先查询知识库，确保数据存在且属于当前租户。
        KnowledgeBase knowledgeBase = getKnowledgeBase(request.getId());
        validateEmbeddingConfig(request.getPipelineConfig());
        if (!isBlank(request.getName())) {
            // 如果传入名称，则更新知识库名称。
            knowledgeBase.setName(request.getName());
        }
        if (request.getDescription() != null) {
            // 如果传入描述，则更新知识库描述，允许设置为空字符串。
            knowledgeBase.setDescription(request.getDescription());
        }
        if (!isBlank(request.getVisibility())) {
            // 如果传入可见性，则更新知识库可见性。
            knowledgeBase.setVisibility(request.getVisibility());
        }
        if (request.getDomainCode() != null) {
            // 更新业务域，允许显式改回 GENERAL。
            knowledgeBase.setDomainCode(normalizeDomain(request.getDomainCode()));
        }
        if (request.getPipelineConfig() != null) {
            // 如果传入流水线配置，则替换知识库的默认配置。
            knowledgeBase.setChunkStrategy(request.getPipelineConfig());
        }
        // 调用 Mapper 按主键更新知识库基础信息。
        knowledgeBaseMapper.updateById(knowledgeBase);
        // 更新后重新查询，返回数据库中的最新数据。
        return getKnowledgeBase(request.getId());
    }

    /**
     * 逻辑删除当前租户下的知识库。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteKnowledgeBase(Long knowledgeBaseId) {
        KnowledgeBase kb = getKnowledgeBase(knowledgeBaseId);

        // 1. 查该知识库下所有文档
        List<KnowledgeDocument> docs = documentMapper.selectList(
                new LambdaQueryWrapper<KnowledgeDocument>()
                        .eq(KnowledgeDocument::getKnowledgeBaseId, knowledgeBaseId)
                        .eq(KnowledgeDocument::getTenantId, kb.getTenantId()));

        for (KnowledgeDocument doc : docs) {
            // 2. 物理删除文档的 Chunk（释放 chunk_index UNIQUE 约束）
            chunkMapper.deleteByDocumentIdPhysically(doc.getId());
            // 3. 逻辑删除文档
            documentMapper.deleteById(doc.getId());
        }

        // 文档全部逻辑删除后将知识库缓存计数归零。
        int updatedRows = knowledgeBaseMapper.resetDocumentCount(
                knowledgeBaseId,
                kb.getTenantId()
        );
        if (updatedRows != 1) {
            throw new ServiceException(
                    BaseErrorCode.DATABASE_ERROR,
                    "重置知识库文档数量失败"
            );
        }

        // 4. 逻辑删除 KB
        knowledgeBaseMapper.deleteById(knowledgeBaseId);

    }

    /**
     * 校验知识库存在且处于启用状态，供后续文档上传、检索和问答流程复用。
     */
    @Override
    public KnowledgeBase ensureUsable(Long knowledgeBaseId) {
        // 先查询知识库，确保数据存在且属于当前租户。
        KnowledgeBase knowledgeBase = getKnowledgeBase(knowledgeBaseId);
        if (!Integer.valueOf(1).equals(knowledgeBase.getStatus())) {
            throw new BusinessException(BaseErrorCode.FORBIDDEN, "知识库不可用");
        }
        return knowledgeBase;
    }
    @Override
    public List<ChatKnowledgeBaseOption> listAvailableForChat() {
        // 从 JWT 上下文获取租户，普通用户不能自行传 tenantId。
        Long tenantId = currentUserProvider.requireTenantId();

        // 只返回当前租户已启用、未删除的知识库。
        return knowledgeBaseMapper.selectAvailableForChat(tenantId)
                .stream()
                .map(knowledgeBase -> ChatKnowledgeBaseOption.builder()
                        .id(knowledgeBase.getId())
                        .name(knowledgeBase.getName())
                        .build())
                .toList();
    }

    private KnowledgeBase selectCurrentTenantKnowledgeBase(Long knowledgeBaseId) {
        // 使用当前租户 ID 拼接查询条件，实现租户级数据隔离。
        return knowledgeBaseMapper.selectOne(new LambdaQueryWrapper<KnowledgeBase>()
                .eq(KnowledgeBase::getId, knowledgeBaseId)
                .eq( KnowledgeBase::getTenantId,
                        currentUserProvider.requireTenantId()));
    }
    /**
     * 归一化业务域编码：空值回退 GENERAL，统一大写。
     */
    private String normalizeDomain(String domainCode) {
        if (isBlank(domainCode)) {
            return "GENERAL";
        }
        return domainCode.trim().toUpperCase();
    }

    private String defaultIfBlank(String value, String defaultValue) {
        return isBlank(value) ? defaultValue : value;
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
    private final ModelConfigMapper modelConfigMapper;
    private final EmbeddingClientProperties embeddingProperties;

    /** 校验知识库绑定的 (模型, 维度) 与数据库列维度兼容。 */
    private void validateEmbeddingConfig(PipelineConfig pipelineConfig) {
        if (pipelineConfig == null
                || pipelineConfig.getEmbeddingModel() == null
                || pipelineConfig.getEmbeddingModel().isBlank()) {
            return; // 未绑定模型，使用全局默认。
        }
        Integer dimension = pipelineConfig.getEmbeddingDimension();
        if (dimension == null) {
            return; // 未指定维度，服务端 fallback 全局配置。
        }
        // 1. 维度必须等于数据库列维度。
        if (!embeddingProperties.getDimension().equals(dimension)) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "所选向量维度 " + dimension + " 与数据库列维度 "
                            + embeddingProperties.getDimension() + " 不兼容，"
                            + "如需更换请先迁移数据库列");
        }
        // 2. 模型必须声明支持该维度。
        List<ModelConfig> configs = modelConfigMapper.selectList(
                new LambdaQueryWrapper<ModelConfig>()
                        .eq(ModelConfig::getModelCode,
                                pipelineConfig.getEmbeddingModel())
                        .eq(ModelConfig::getModelType, "EMBEDDING")
                        .eq(ModelConfig::getStatus, 1));
        boolean supported = configs.stream()
                .anyMatch(c -> parseDimensions(c.getParameters())
                        .contains(dimension));
        if (!supported) {
            throw new ClientException(
                    BaseErrorCode.BAD_REQUEST,
                    "模型 " + pipelineConfig.getEmbeddingModel()
                            + " 不支持 " + dimension + " 维");
        }
    }
    private List<Integer> parseDimensions(String parameters) {
        if (parameters == null || parameters.isBlank()) {
            return List.of();
        }
        try {
            JsonNode node = objectMapper.readTree(parameters);
            JsonNode dims = node.get("dimensions");
            if (dims != null && dims.isArray()) {
                List<Integer> result = new ArrayList<>();
                for (JsonNode d : dims) {
                    result.add(d.asInt());
                }
                return result;
            }
            // 兼容旧单值 {"dimension":1536}
            JsonNode single = node.get("dimension");
            if (single != null && single.isInt()) {
                return List.of(single.asInt());
            }
        } catch (Exception ex) {
            log.warn("解析模型维度失败, parameters={}", parameters, ex);
        }
        return List.of();
    }
}
