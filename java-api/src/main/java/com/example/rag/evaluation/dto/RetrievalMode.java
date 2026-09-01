package com.example.rag.evaluation.dto;

/**
 * 检索调试模式。
 */
public enum RetrievalMode {

    /** 只执行 pgvector 向量检索。 */
    VECTOR,

    /** 只执行 PostgreSQL 关键词检索。 */
    KEYWORD,

    /** 同时执行两路检索，并通过 RRF 融合。 */
    HYBRID
}