"""检索公共工具：关键词合并、候选转 Document。

HybridRetriever 与 RetrievalDebugService 共用，避免逻辑重复。
"""

from langchain_core.documents import Document

from app.rag.schemas.retrieval_schema import RetrievalCandidate


def merge_keywords(
    keywords: list[str],
    synonym_keywords: list[str] | None = None,
) -> list[str]:
    """合并关键词与同义词变体，去重后返回。"""
    merged = list(keywords)
    if synonym_keywords:
        merged.extend(synonym_keywords)

    seen: set[str] = set()
    result: list[str] = []
    for keyword in merged:
        key = keyword.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(keyword)
    return result


def candidate_to_document(
    candidate: RetrievalCandidate,
) -> Document:
    """将检索候选转换为 LangChain Document。"""
    return Document(
        page_content=candidate.content,
        metadata={
            "chunk_id": candidate.chunk_id,
            "document_id": candidate.document_id,
            "knowledge_base_id": candidate.knowledge_base_id,
            "chunk_index": candidate.chunk_index,
            "document_name": candidate.document_name,
            "score": candidate.fusion_score,
            "fusion_score": candidate.fusion_score,
            "vector_score": candidate.vector_score,
            "keyword_score": candidate.keyword_score,
            "vector_rank": candidate.vector_rank,
            "keyword_rank": candidate.keyword_rank,
            "retrieval_sources": candidate.retrieval_sources,
            "metadata": candidate.metadata,
        },
    )
