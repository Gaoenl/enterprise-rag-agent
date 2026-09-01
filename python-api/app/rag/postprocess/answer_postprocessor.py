"""模型回答清理与引用编号校验。"""

import re

from langchain_core.documents import Document

from app.schemas.answer_schema import (
    AnswerPostProcessResult,
    AnswerStatus,
)


class AnswerPostProcessor:
    """清理模型回答并检查 [来源 N]。"""

    _CITATION_PATTERN = re.compile(
        r"\[来源\s*(\d+)\]"
    )

    def process(
            self,
            answer: str,
            documents: list[Document],
            rag_mode: bool,
            no_evidence: bool = False,
    ) -> AnswerPostProcessResult:
        """执行回答后处理。"""
        normalized_answer = answer.strip()

        # 普通聊天不要求知识库引用。
        if not rag_mode:
            return AnswerPostProcessResult(
                answer=normalized_answer,
                answer_status=AnswerStatus.GENERAL,
            )

        # RAG 无有效上下文。
        if no_evidence or not documents:
            return AnswerPostProcessResult(
                answer=normalized_answer,
                answer_status=AnswerStatus.NO_EVIDENCE,
            )
        valid_indexes = {
            int(document.metadata["citation_index"])
            for document in documents
            if document.metadata.get("citation_index")
               is not None
        }

        used_indexes: list[int] = []
        invalid_indexes: list[int] = []

        def replace_citation(
                match: re.Match[str],
        ) -> str:
            """保留有效引用，删除无效引用标记。"""
            citation_index = int(match.group(1))

            if citation_index in valid_indexes:
                if citation_index not in used_indexes:
                    used_indexes.append(citation_index)

                # 统一引用格式。
                return f"[来源 {citation_index}]"

            if citation_index not in invalid_indexes:
                invalid_indexes.append(citation_index)

            # 无效引用标记直接删除。
            return ""

        cleaned_answer = self._CITATION_PATTERN.sub(
            replace_citation,
            normalized_answer,
        )

        # 清理由删除无效引用产生的多余空格。
        cleaned_answer = re.sub(
            r"[ \t]{2,}",
            " ",
            cleaned_answer,
        ).strip()

        return AnswerPostProcessResult(
            answer=cleaned_answer,
            answer_status=AnswerStatus.ANSWERED,
            used_citation_indexes=used_indexes,
            invalid_citation_indexes=invalid_indexes,
        )