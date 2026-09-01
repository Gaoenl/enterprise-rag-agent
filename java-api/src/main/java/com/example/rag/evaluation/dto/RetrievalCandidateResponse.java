package com.example.rag.evaluation.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 某个检索阶段返回的候选分片。
 */
@Data
public class RetrievalCandidateResponse {

    /** 分片 ID。 */
    private Long chunkId;

    /** 所属文档 ID。 */
    private Long documentId;

    /** 所属知识库 ID。 */
    private Long knowledgeBaseId;

    /** 分片在文档中的序号。 */
    private Integer chunkIndex;

    /** 文档文件名。 */
    private String documentName;

    /** 分片正文。 */
    private String content;

    /** 向量余弦相似度。 */
    private Double vectorScore;

    /** 关键词命中得分。 */
    private Double keywordScore;

    /** RRF 融合得分。 */
    private Double fusionScore;

    /** Rerank 相关性得分。 */
    private Double rerankScore;

    /** 向量检索排名。 */
    private Integer vectorRank;

    /** 关键词检索排名。 */
    private Integer keywordRank;

    /** RRF 融合后排名。 */
    private Integer fusionRank;

    /** Rerank 后排名。 */
    private Integer rerankRank;

    /** 该分片的召回来源。 */
    private List<String> retrievalSources;

    /** 分片原始 metadata。 */
    private Map<String, Object> metadata;

    /** 进入最终上下文后的引用编号。 */
    private Integer citationIndex;

    /** 进入上下文时是否被截断。 */
    private Boolean contextTruncated;
}