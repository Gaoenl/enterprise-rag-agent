package com.example.rag.knowledge.service;

import com.example.rag.knowledge.entity.KnowledgeDocument;
import com.example.rag.knowledge.entity.KnowledgeDocumentChunk;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * 知识库文档服务接口。
 *
 * <p>文档服务负责文档元数据登记和解析状态流转，真正的解析、切片、向量化会在后续入库任务中完成。</p>
 */
public interface KnowledgeDocumentService {

    /**
     * 批量上传文件到对象存储，并为每个文件分别创建文档和入库任务。
     *
     * @param knowledgeBaseId 知识库 ID
     * @param files 待上传文件列表
     * @param metadata 公共元数据
     * @return 已创建的文档列表
     */
    List<KnowledgeDocument> uploadDocuments(
            Long knowledgeBaseId,
            List<MultipartFile> files,
            String metadata
    );

    /**
     * 上传文件到对象存储，并登记文档元数据。
     */
    KnowledgeDocument uploadDocument(Long knowledgeBaseId, MultipartFile file,
                                     String metadata);
    /**
     * 登记文档元数据。
     *
     * <p>实际用途：文件上传成功后，先在数据库中创建文档记录，再创建入库任务。</p>
     */
    KnowledgeDocument registerDocument(KnowledgeDocument document);

    /**
     * 查询文档详情。
     *
     * <p>实际用途：文档管理页查看文件信息，或入库任务根据文档 ID 回查元数据。</p>
     */
    KnowledgeDocument getDocument(Long documentId);

    /**
     * 查询知识库下的文档列表。
     *
     * <p>实际用途：知识库详情页展示已上传文档，以及后续批量重新入库。</p>
     */
    List<KnowledgeDocument> listByKnowledgeBase(Long knowledgeBaseId);

    /**
     * 更新文档解析状态。
     *
     * <p>实际用途：入库任务执行解析、切片、向量化时，持续更新文档状态给前端展示。</p>
     */
    void markParseStatus(Long documentId, String parseStatus);

    /**
     * 删除文档。
     *
     * <p>实际用途：管理端移除文档；底层应走逻辑删除，避免误删审计和历史任务数据。</p>
     */
    void deleteDocument(Long documentId);

    /**
     * 批量逻辑删除文档（仅当前租户，已删除/不存在的自动跳过）。
     *
     * @param documentIds 文档 ID 列表
     */
    void batchDeleteDocuments(List<Long> documentIds);

    List<KnowledgeDocumentChunk> listDocumentChunks(
            Long documentId
    );

}
