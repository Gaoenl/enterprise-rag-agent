"""在当前租户允许访问的范围内选择知识库。"""

from app.rag.db.postgres import get_connection
from app.rag.schemas.routing_schema import (
    KnowledgeBaseCandidate,
    KnowledgeBaseSelection,
)


class KnowledgeBaseSelector:
    """知识库候选查询和选择服务。"""

    def select(
        self,
        tenant_id: int | None,
        user_id: int | None,
        preferred_knowledge_base_id: int | None,
        query: str,
        domain: str | None = None,
    ) -> KnowledgeBaseSelection:
        """为当前 RAG 请求选择一个知识库。"""
        if tenant_id is None:
            return KnowledgeBaseSelection(
                selection_type="MISSING_TENANT",
                confidence=1.0,
                need_clarification=True,
                reason="RAG 查询缺少 tenantId，无法保证租户隔离。",
            )

        # 用户明确指定知识库时，只校验该知识库，不按域过滤、不自动替换。
        if preferred_knowledge_base_id is not None:
            candidate = self._find_specified_knowledge_base(
                tenant_id=tenant_id,
                knowledge_base_id=preferred_knowledge_base_id,
            )
            if candidate is None:
                return KnowledgeBaseSelection(
                    selection_type="INVALID_SPECIFIED",
                    confidence=1.0,
                    need_clarification=True,
                    reason="指定知识库不存在、已禁用或不属于当前租户。",
                )
            return KnowledgeBaseSelection(
                knowledge_base_id=candidate.id,
                selection_type="USER_SPECIFIED",
                confidence=1.0,
                need_clarification=False,
                reason="使用用户明确选择的知识库。",
                candidates=[candidate],
            )

        # 自动选择：按业务域过滤候选。
        domain_code = (domain or "GENERAL").upper()
        candidates = self._find_tenant_knowledge_bases(
            tenant_id, domain_code
        )

        # 域内没有知识库时，降级到 GENERAL 域。
        if not candidates and domain_code != "GENERAL":
            candidates = self._find_tenant_knowledge_bases(
                tenant_id, "GENERAL"
            )

        # GENERAL 域仍为空时，回退到租户全部可用知识库。
        if not candidates:
            candidates = self._find_tenant_knowledge_bases(
                tenant_id, None
            )

        if not candidates:
            return KnowledgeBaseSelection(
                selection_type="NO_AVAILABLE",
                confidence=1.0,
                need_clarification=True,
                reason="当前租户没有可用知识库。",
            )

        # 只有一个候选项时可以直接选择。
        if len(candidates) == 1:
            return KnowledgeBaseSelection(
                knowledge_base_id=candidates[0].id,
                selection_type="ONLY_AVAILABLE",
                confidence=1.0,
                need_clarification=False,
                reason="当前租户只有一个可用知识库。",
                candidates=candidates,
            )

        # 第一版先使用名称和描述的简单匹配。
        matched_candidates = [
            candidate
            for candidate in candidates
            if candidate.name in query
            or (
                candidate.description is not None
                and candidate.description.strip()
                and candidate.description.strip() in query
            )
        ]

        if len(matched_candidates) == 1:
            return KnowledgeBaseSelection(
                knowledge_base_id=matched_candidates[0].id,
                selection_type="TEXT_MATCHED",
                confidence=0.85,
                need_clarification=False,
                reason="问题命中了知识库名称或描述。",
                candidates=matched_candidates,
            )

        # 多个知识库无法可靠判断时，交给用户选择。
        return KnowledgeBaseSelection(
            selection_type="MULTIPLE_CANDIDATES",
            confidence=0.0,
            need_clarification=True,
            reason="存在多个可用知识库，当前无法可靠确定检索范围。",
            candidates=candidates,
        )


    @staticmethod
    def _find_specified_knowledge_base(
        tenant_id: int,
        knowledge_base_id: int,
    ) -> KnowledgeBaseCandidate | None:
        """校验指定知识库是否属于当前租户，返回单个候选或 None。"""
        sql = """
            SELECT id, name, description
            FROM kb_knowledge_base
            WHERE id = %s
              AND tenant_id = %s
              AND deleted = false
              AND status = 1
            LIMIT 1
        """

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (knowledge_base_id, tenant_id))
                row = cursor.fetchone()

        if row is None:
            return None

        return KnowledgeBaseCandidate(
            id=row[0],
            name=row[1],
            description=row[2],
        )

    @staticmethod
    def _find_tenant_knowledge_bases(
        tenant_id: int,
        domain_code: str | None,
    ) -> list[KnowledgeBaseCandidate]:
        """查询当前租户下可使用的知识库。

        domain_code 为 None 时不按域过滤（回退全部）；
        否则精确匹配该业务域。
        """
        sql = """
            SELECT id, name, description
            FROM kb_knowledge_base
            WHERE tenant_id = %s
              AND deleted = false
              AND status = 1
        """
        params: list[object] = [tenant_id]

        if domain_code is not None:
            sql += " AND domain_code = %s"
            params.append(domain_code)

        sql += " ORDER BY updated_at DESC"

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()

        return [
            KnowledgeBaseCandidate(
                id=row[0],
                name=row[1],
                description=row[2],
            )
            for row in rows
        ]