package com.example.rag.ingestion.service;

import com.example.rag.knowledge.entity.KnowledgeDocumentChunk;
import com.example.rag.knowledge.mapper.KnowledgeDocumentChunkMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class ChunkPersistenceService {

    private final KnowledgeDocumentChunkMapper chunkMapper;

    /**
     * 删除旧 Chunk 并保存新 Chunk。
     *
     * <p>两步必须位于同一个短事务中，避免删除成功但插入失败。</p>
     */
    @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            rollbackFor = Exception.class
    )
    public void replaceDocumentChunks(
            Long documentId,
            List<KnowledgeDocumentChunk> chunks
    ) {
        chunkMapper.deleteByDocumentIdPhysically(
                documentId
        );

        if (chunks == null || chunks.isEmpty()) {
            return;
        }

        chunkMapper.insert(chunks);
    }
}