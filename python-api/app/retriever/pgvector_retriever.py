from langchain_core.documents import Document

from app.config import get_settings
from app.clients.embedding_client import EmbeddingClient
from app.db.postgres import get_connection
from app.schemas.retrieval_schema import RetrievalCandidate


class PgVectorRetriever:
    """基于项目自定义 kb_document_chunk 表的 pgvector 检索器。"""
    def __init__(self):
        self._settings= get_settings()
        self._embedding_client = EmbeddingClient()
    def retrieve(self,
                 question: str,
                 tenant_id: int,
                 knowledge_base_id: int | None = None,
                 top_k: int | None = None)-> list[Document]:
        # 1. 解析知识库绑定的 (模型, 维度)，保证与库内向量同一空间。
        model, dimension = self._resolve_embedding_config(knowledge_base_id)

        # 2. 用知识库模型向量化查询。
        query_vector = self._embedding_client.embed_query(
            question,
            model=model,
            dimension=dimension,
        )
        # 3. pgvector 接收形如 [0.1,0.2,...] 的向量字符串。
        vector_text  ="["+ ",".join([str(x) for x in query_vector])+"]"
        # 3. 控制召回数量。
        limit = top_k or self._settings.retrieval_vector_top_k
        sql = """
            SELECT
                chunk.id,
                chunk.document_id,
                chunk.knowledge_base_id,
                chunk.chunk_index,
                chunk.content,
                document.file_name,
                1 - (embedding <=> %s::vector) AS score,
                chunk.metadata
            FROM kb_document_chunk chunk
            INNER JOIN kb_document document
                ON document.id = chunk.document_id
               AND document.tenant_id = chunk.tenant_id
               AND document.deleted = false
            WHERE chunk.tenant_id = %s
              AND chunk.deleted = false
              AND chunk.embedding IS NOT NULL
        """
        params: list[object] = [vector_text, tenant_id]
        if knowledge_base_id is not None:
            sql += " AND chunk.knowledge_base_id = %s"
            sql += " AND chunk.embedding_model = %s"
            sql += " AND chunk.embedding_dimension = %s"
            params.extend([knowledge_base_id, model, dimension])
        sql += """
            ORDER BY chunk.embedding <=> %s::vector
            LIMIT %s
        """
        params.extend([vector_text, limit])
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        candidates: list[RetrievalCandidate] = []
        for rank, row in enumerate(rows, start=1):
            candidates.append(
                RetrievalCandidate(
                    chunk_id=row[0],
                    document_id=row[1],
                    knowledge_base_id=row[2],
                    chunk_index=row[3],
                    content=row[4],
                    document_name=row[5],
                    vector_score=float(row[6]),
                    vector_rank=rank,
                    retrieval_sources=["vector"],
                    metadata=row[7] or {},
                )
            )
        return candidates

    def _resolve_embedding_config(
            self,
            knowledge_base_id: int | None,
    ) -> tuple[str, int]:
        """读取知识库绑定 (embeddingModel, embeddingDimension)，缺失时用全局配置。"""
        # 未指定知识库：直接使用全局默认模型与维度。
        if knowledge_base_id is None:
            return (
                self._settings.embedding_model,
                self._settings.embedding_dimension,
            )
        sql = """
               SELECT chunk_strategy->>'embeddingModel',
                      chunk_strategy->>'embeddingDimension'
               FROM kb_knowledge_base
               WHERE id = %s
                 AND deleted = false
                 AND status = 1
               LIMIT 1
           """
        model: str | None = None
        dimension: int | None = None
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (knowledge_base_id,))
                row = cursor.fetchone()
        if row is not None:
            model = row[0] or None
            dimension = int(row[1]) if row[1] else None
        return (
            model or self._settings.embedding_model,
            dimension if dimension is not None else self._settings.embedding_dimension,
        )

