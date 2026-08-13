"""将精排后的文档分片打包为 LLM 上下文。"""

import hashlib
import re

from langchain_core.documents import Document

from app.config import get_settings
from app.schemas.context_schema import PackedContext


class ContextPacker:
    """负责分片去重、预算控制和引用编号。"""

    def __init__(self) -> None:
        """读取上下文打包配置。"""
        self._settings = get_settings()

    def pack(
        self,
        documents: list[Document],
    ) -> PackedContext:
        """将候选分片打包为带来源编号的上下文。"""
        if not documents:
            return PackedContext()

        max_context_chars = self._settings.rag_max_context_chars
        max_document_chars = (
            self._settings.rag_context_max_document_chars
        )

        if max_context_chars <= 0:
            return PackedContext(
                truncated=bool(documents),
            )

        parts: list[str] = []
        packed_documents: list[Document] = []

        # 按 chunk_id 去重。
        seen_chunk_ids: set[object] = set()

        # 按规范化后的正文哈希去重。
        seen_content_hashes: set[str] = set()

        truncated = False

        for document in documents:
            original_content = document.page_content.strip()

            # 空内容不进入上下文。
            if not original_content:
                continue

            chunk_id = document.metadata.get("chunk_id")

            # 相同 chunk_id 只保留第一次出现的分片。
            if chunk_id is not None and chunk_id in seen_chunk_ids:
                continue

            # 对空白字符规范化后计算内容哈希。
            content_hash = self._content_hash(original_content)

            # 完全相同的正文只保留一次。
            if content_hash in seen_content_hashes:
                continue

            # 只有确定接收该分片后才写入 seen 集合。
            citation_index = len(packed_documents) + 1

            header = self._build_header(
                citation_index=citation_index,
                document=document,
            )

            # 单个分片先执行自身字符限制。
            limited_content = original_content[
                :max_document_chars
            ]

            document_was_truncated = (
                len(limited_content) < len(original_content)
            )

            full_block = self._build_block(
                header=header,
                content=limited_content,
                content_truncated=document_was_truncated,
            )

            # 非第一个来源块之前需要两个换行符。
            separator = "\n\n" if parts else ""

            current_text_length = sum(
                len(part) for part in parts
            )

            # parts 中不保存 separator，因此还要计算已有分隔符。
            if len(parts) > 1:
                current_text_length += 2 * (len(parts) - 1)

            required_chars = len(separator) + len(full_block)

            if (
                current_text_length + required_chars
                <= max_context_chars
            ):
                # 当前分片可以完整放入剩余预算。
                packed_content = limited_content
                packed_block = full_block
            else:
                # 计算当前分片可以使用的剩余预算。
                remaining_chars = (
                    max_context_chars
                    - current_text_length
                    - len(separator)
                )

                packed_content, packed_block = (
                    self._truncate_block_to_budget(
                        header=header,
                        content=limited_content,
                        remaining_chars=remaining_chars,
                    )
                )

                truncated = True

                # 连标题都放不下时停止继续打包。
                if not packed_block:
                    break

            # 复制 metadata，避免修改 Rerank 返回对象。
            metadata = dict(document.metadata)

            # 记录该分片对应的引用编号。
            metadata["citation_index"] = citation_index

            # 标记该分片进入上下文时是否被截断。
            metadata["context_truncated"] = (
                document_was_truncated
                or len(packed_content) < len(limited_content)
            )

            # PackedContext 中保存的正文必须与模型实际看到的一致。
            packed_document = Document(
                page_content=packed_content,
                metadata=metadata,
            )

            parts.append(packed_block)
            packed_documents.append(packed_document)

            if chunk_id is not None:
                seen_chunk_ids.add(chunk_id)

            seen_content_hashes.add(content_hash)

            # 当前分片因为总预算被截断后，已经没有空间继续添加。
            if len(packed_content) < len(limited_content):
                break

        # 如果没有装入全部有效候选，标记发生截断。
        if len(packed_documents) < len(documents):
            truncated = True

        context_text = "\n\n".join(parts)

        return PackedContext(
            text=context_text,
            documents=packed_documents,
            total_chars=len(context_text),
            truncated=truncated,
        )

    def _build_header(
        self,
        citation_index: int,
        document: Document,
    ) -> str:
        """构建单个来源块的标题信息。"""
        metadata = document.metadata

        document_name = (
            metadata.get("document_name")
            or "未知文档"
        )
        document_id = metadata.get(
            "document_id",
            "N/A",
        )
        chunk_index = metadata.get(
            "chunk_index",
            "N/A",
        )

        lines = [
            f"[来源 {citation_index}]",
            f"文档名称：{document_name}",
            f"文档 ID：{document_id}",
            f"分片序号：{chunk_index}",
        ]

        # 检索分数只在明确启用时写入上下文。
        if self._settings.rag_context_include_scores:
            rerank_score = metadata.get("rerank_score")

            if rerank_score is not None:
                lines.append(
                    f"相关性分数：{float(rerank_score):.4f}"
                )

        lines.append("正文：")

        return "\n".join(lines)

    @staticmethod
    def _build_block(
        header: str,
        content: str,
        content_truncated: bool,
    ) -> str:
        """将标题和正文组合成完整来源块。"""
        block = f"{header}\n{content}"

        if content_truncated:
            block += "\n[内容已截断]"

        return block

    @staticmethod
    def _truncate_block_to_budget(
        header: str,
        content: str,
        remaining_chars: int,
    ) -> tuple[str, str]:
        """将当前来源块截断到剩余字符预算内。"""
        truncated_marker = "\n[内容已截断]"

        # 标题、换行和截断标记也必须计入预算。
        fixed_chars = (
            len(header)
            + 1
            + len(truncated_marker)
        )

        available_content_chars = (
            remaining_chars - fixed_chars
        )

        # 连最小来源块都放不下时不再添加。
        if available_content_chars <= 0:
            return "", ""

        packed_content = content[
            :available_content_chars
        ]

        packed_block = (
            f"{header}\n"
            f"{packed_content}"
            f"{truncated_marker}"
        )

        return packed_content, packed_block

    @staticmethod
    def _content_hash(content: str) -> str:
        """计算规范化正文的 SHA-256。"""
        # 将连续空白统一为一个空格，避免只因换行不同而重复。
        normalized = re.sub(
            r"\s+",
            " ",
            content,
        ).strip()

        return hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()