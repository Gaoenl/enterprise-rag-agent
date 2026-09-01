"""Rerank 业务服务。"""
import logging
from langchain_core.documents import Document

from app.rag.clients.rerank_client import RerankClient
from app.config import get_settings


logger = logging.getLogger(__name__)


class RerankService:
    """编排候选截断、模型排序、结果映射和失败降级。"""

    def __init__(self) -> None:
        """初始化 Rerank 依赖。"""
        self._settings = get_settings()
        self._client = RerankClient()
    def rerank(self, query: str, documents: list[Document]) -> list[Document]:
        """对混合检索候选分片执行精排。"""
        if not documents:
            return []
        # Rerank 关闭时，直接使用 RRF 排名的前 N 条。
        if not self._settings.rerank_enabled:
            return self._fallback(documents)
        # 限制进入 Rerank 的候选数量。
        candidates = documents[
                     :self._settings.rerank_candidate_top_k
                     ]
        # 只截断发给排序模型的文本，不修改原始 Document
        document_texts = [
            document.page_content[
            :self._settings.rerank_max_document_chars
            ]
            for document in candidates
        ]
        try:
            # 调用真实 Rerank 模型。
            results = self._client.rerank(
                query=query,
                documents=document_texts,
                top_n=self._settings.rerank_final_top_k,
            )

            reranked_documents: list[Document] = []
            used_indexes: set[int] = set()

            for rank, result in enumerate(results, start=1):
                # 防止外部接口返回越界 index。
                if result.index < 0 or result.index >= len(candidates):
                    logger.warning(
                        "Ignore invalid rerank index, index=%s, size=%s",
                        result.index,
                        len(candidates),
                    )
                    continue

                # 防止外部接口重复返回相同候选。
                if result.index in used_indexes:
                    logger.warning(
                        "Ignore duplicated rerank index, index=%s",
                        result.index,
                    )
                    continue

                used_indexes.add(result.index)

                original = candidates[result.index]

                # 复制 metadata，避免修改原始候选对象。
                metadata = dict(original.metadata)
                metadata["rerank_score"] = result.relevance_score
                metadata["rerank_rank"] = rank

                reranked_documents.append(
                    Document(
                        page_content=original.page_content,
                        metadata=metadata,
                    )
                )
                # 所有返回项均无效时，降级使用 RRF。
            if not reranked_documents:
                logger.warning(
                    "Rerank returned no valid documents, fallback to RRF"
                )
                return self._fallback(documents)

            return reranked_documents
        except Exception:
            # Rerank 是质量增强步骤，失败不能中断 RAG。
            logger.exception(
                "Rerank failed, fallback to RRF ranking"
            )
            return self._fallback(documents)

    def _fallback(
            self,
            documents: list[Document],
    ) -> list[Document]:
        """使用原始 RRF 顺序返回最终候选。"""
        final_top_k = self._settings.rerank_final_top_k

        return documents[:final_top_k]