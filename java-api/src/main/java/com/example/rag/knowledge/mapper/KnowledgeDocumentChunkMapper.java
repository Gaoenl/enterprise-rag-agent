package com.example.rag.knowledge.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.rag.knowledge.entity.KnowledgeDocumentChunk;
import org.apache.ibatis.annotations.*;

import java.util.List;

/**
 * 文档 Chunk Mapper。
 */
@Mapper
public interface KnowledgeDocumentChunkMapper extends BaseMapper<KnowledgeDocumentChunk> {

    /**
     * 物理删除指定文档下的所有 Chunk。
     *
     * 这里不用逻辑删除，是为了避免 unique(document_id, chunk_index) 冲突。
     */
    @Delete("delete from kb_document_chunk where document_id = #{documentId}")
    void deleteByDocumentIdPhysically(@Param("documentId") Long documentId);
    /**
     * 查询指定文档下尚未生成向量的 Chunk。
     */
    @Select("""
    select id,
           tenant_id,
           knowledge_base_id,
           document_id,
           chunk_index,
           content,
           token_count,
           embedding_model,
           metadata,
           created_at,
           updated_at,
           deleted
    from kb_document_chunk
    where document_id = #{documentId}
      and deleted = false
      and embedding is null
    order by chunk_index asc
""")
    List<KnowledgeDocumentChunk> selectWithoutEmbeddingByDocumentId(@Param("documentId") Long documentId);

    /**
     * 更新 Chunk 向量。
     */
    @Update("""
    update kb_document_chunk
    set embedding = #{embedding}::vector,
        embedding_model = #{embeddingModel},
        embedding_dimension = #{embeddingDimension},
        updated_at = now()
    where id = #{chunkId}
""")
    void updateEmbedding(@Param("chunkId") Long chunkId,
                         @Param("embedding") String embedding,
                         @Param("embeddingModel") String embeddingModel,
                         @Param("embeddingDimension") Integer embeddingDimension);
}