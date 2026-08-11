"""基于 PostgreSQL pg_trgm 和 ILIKE 的关键词检索器。"""
from app.config import get_settings
from app.db.postgres import get_connection
from app.schemas.retrieval_schema import RetrievalCandidate


class KeywordRetriever:
    """对文档内容和文件名执行关键词包含检索。"""

    def __init__(self) -> None:
        """读取关键词检索配置。"""
        self._settings = get_settings()

    def retrieve(
            self,
            keywords: list[str],
            tenant_id: int,
            knowledge_base_id: int | None = None,
            top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """执行关键词检索。"""
        normalized_keywords = self._normalize_keywords(keywords)
        if not normalized_keywords:
            return []
        limit = top_k or self._settings.retrieval_keyword_top_k
        # 每个关键词生成一项内容命中得分。
        content_score_parts=[
            "CASE WHEN chunk.content ILIKE %s ESCAPE '\\' THEN 1 ELSE 0 END" for _ in normalized_keywords
        ]
        # 文件名命中的权重高于正文命中。
        file_name_score_parts = [
            "CASE WHEN document.file_name ILIKE %s ESCAPE '\\' THEN 2 ELSE 0 END"
            for _ in normalized_keywords
        ]
        # 任意关键词命中正文或文件名即可成为候选结果。
        where_parts = [
            (
                "chunk.content ILIKE %s ESCAPE '\\' "
                "OR document.file_name ILIKE %s ESCAPE '\\'"
            )
            for _ in normalized_keywords
        ]
        score_expression = " + ".join(
            content_score_parts + file_name_score_parts
        )
        where_expression = " OR ".join(where_parts)

        sql = f"""
            SELECT
                chunk.id,
                chunk.document_id,
                chunk.knowledge_base_id,
                chunk.chunk_index,
                chunk.content,
                document.file_name,
                ({score_expression})::double precision AS keyword_score,
                chunk.metadata
            FROM kb_document_chunk chunk
            INNER JOIN kb_document document
                ON document.id = chunk.document_id
               AND document.tenant_id = chunk.tenant_id
               AND document.deleted = false
            WHERE chunk.tenant_id = %s
              AND chunk.deleted = false
              AND ({where_expression})
        """
        # 未指定知识库时不按知识库过滤（全租户检索）。
        if knowledge_base_id is not None:
            sql += " AND chunk.knowledge_base_id = %s"
        sql += """
            ORDER BY keyword_score DESC, chunk.id ASC
            LIMIT %s
        """
        patterns = [
            self._build_like_pattern(keyword)
            for keyword in normalized_keywords
        ]

        parameters: list[object] = []

        # content_score_parts 对应的参数。
        parameters.extend(patterns)

        # file_name_score_parts 对应的参数。
        parameters.extend(patterns)

        # 对应 WHERE chunk.tenant_id = %s。
        parameters.append(tenant_id)

        # WHERE 中每个关键词使用两次。
        for pattern in patterns:
            parameters.extend([pattern, pattern])

        if knowledge_base_id is not None:
            # 对应 WHERE 之后的 AND chunk.knowledge_base_id = %s。
            parameters.append(knowledge_base_id)

        # 补充 LIMIT 参数。
        parameters.append(limit)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
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
                      keyword_score=float(row[6]),
                      keyword_rank=rank,
                      retrieval_sources=["keyword"],
                      metadata=row[7] or {},
                  )
              )
        return candidates

    @staticmethod
    def _normalize_keywords(keywords: list[str]) -> list[str]:
        """清理空值和重复关键词。"""
        values: list[str] = []
        seen: set[str] = set()

        for keyword in keywords:
            value = keyword.strip()

            if len(value) < 2 or value in seen:
                continue

            seen.add(value)
            values.append(value)

        return values[:6]

    @staticmethod
    def _build_like_pattern(keyword: str) -> str:
        """转义 LIKE 中具有特殊含义的字符。"""
        escaped = (
            keyword
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        return f"%{escaped}%"
