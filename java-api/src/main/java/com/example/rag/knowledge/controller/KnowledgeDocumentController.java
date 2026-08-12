package com.example.rag.knowledge.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.rag.common.api.ApiResult;
import com.example.rag.knowledge.dto.KnowledgeDocumentRegisterRequest;
import com.example.rag.knowledge.entity.KnowledgeDocument;
import com.example.rag.knowledge.entity.KnowledgeDocumentChunk;
import com.example.rag.knowledge.mapper.KnowledgeDocumentChunkMapper;
import com.example.rag.knowledge.service.KnowledgeDocumentService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * 知识库文档管理接口。
 */
@RestController
@RequestMapping("/api/documents")
@PreAuthorize("hasAnyRole('PLATFORM_ADMIN', 'ADMIN')")
@RequiredArgsConstructor
public class KnowledgeDocumentController {

    private final KnowledgeDocumentService documentService;



    /**
     * 上传文件并登记文档元数据。
     */
    @PostMapping("/upload")
    public ApiResult<List<KnowledgeDocument>> uploadDocuments(
            @RequestParam("knowledgeBaseId") Long knowledgeBaseId,
            @RequestParam("file") List<MultipartFile> files,
            @RequestParam(required = false, value = "metadata") String metadata
    ) {
        // 一个或多个同名 file 字段都会被 Spring 转换为文件列表。
        return ApiResult.ok(
                documentService.uploadDocuments(
                        knowledgeBaseId,
                        files,
                        metadata
                )
        );
    }
    /**
     * 登记文档元数据。
     */
    @PostMapping
    public ApiResult<KnowledgeDocument> registerDocument(@RequestBody KnowledgeDocumentRegisterRequest request) {
        KnowledgeDocument document = KnowledgeDocument.builder()
                .knowledgeBaseId(request.getKnowledgeBaseId())
                .fileName(request.getFileName())
                .fileType(request.getFileType())
                .fileUri(request.getFileUri())
                .fileSize(request.getFileSize())
                .contentHash(request.getContentHash())
                .parseStatus(request.getParseStatus())
                .metadata(request.getMetadata())
                .build();
        return ApiResult.ok(documentService.registerDocument(document));
    }
    /**
     * 查询文档详情。
     */
    @GetMapping("/{documentId}")
    public ApiResult<KnowledgeDocument> getDocument(@PathVariable("documentId") Long documentId) {
        return ApiResult.ok(documentService.getDocument(documentId));
    }

    /**
     * 查询指定知识库下的文档列表。
     */
    @GetMapping("/by-knowledge-base/{knowledgeBaseId}")
    public ApiResult<List<KnowledgeDocument>> listByKnowledgeBase(@PathVariable("knowledgeBaseId") Long knowledgeBaseId) {
        return ApiResult.ok(documentService.listByKnowledgeBase(knowledgeBaseId));
    }

    /**
     * 更新文档解析状态。
     */
    @PatchMapping("/{documentId}/parse-status")
    public ApiResult<Void> markParseStatus(@PathVariable("documentId") Long documentId,
                                           @RequestParam("parseStatus") String parseStatus) {
        documentService.markParseStatus(documentId, parseStatus);
        return ApiResult.ok();
    }

    /**
     * 逻辑删除文档。
     */
    @DeleteMapping("/{documentId}")
    public ApiResult<Void> deleteDocument(@PathVariable("documentId") Long documentId) {
        documentService.deleteDocument(documentId);
        return ApiResult.ok();
    }
    /**
     * 批量逻辑删除文档。
     */
    @PostMapping("/batch-delete")
    public ApiResult<Void> batchDeleteDocuments(
            @RequestBody List<Long> documentIds
    ) {
        documentService.batchDeleteDocuments(documentIds);
        return ApiResult.ok();
    }
    /**
     * 查询文档 Chunk 列表。
     */
    @GetMapping("/{documentId}/chunks")
    public ApiResult<List<KnowledgeDocumentChunk>> listChunks(@PathVariable("documentId") Long documentId) {
        return ApiResult.ok(documentService.listDocumentChunks(documentId));
    }
}
