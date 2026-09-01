"""CRUD-RAG V1 可控测评数据准备器。"""

import hashlib
import heapq
import json
import random
import re
from pathlib import Path
from typing import Iterable

from app.apps.evaluation.models import (
    CorpusDocument,
    EvaluationCase,
    EvaluationTaskType,
    PreparedDatasetSummary,
)


class CrudDatasetPreparer:
    """抽取单文档问答，并构建包含干扰文档的测评语料。"""

    def __init__(
        self,
        crud_root: Path,
        output_dir: Path,
        case_count: int = 50,
        negative_count: int = 450,
        hard_negative_per_case: int = 0,
        random_seed: int = 20260805,
    ) -> None:
        self._crud_root = crud_root.resolve()
        self._output_dir = output_dir.resolve()
        self._case_count = case_count
        self._negative_count = negative_count
        self._hard_negative_per_case = hard_negative_per_case
        self._random_seed = random_seed
        self._random = random.Random(random_seed)

    def prepare(self) -> PreparedDatasetSummary:
        """生成 Case、文档文件、Manifest 和统计摘要。"""
        self._validate_paths()
        self._create_output_directories()

        # 读取并固定抽取单文档问答样本。
        source_cases = self._load_source_cases()
        selected_cases = self._select_cases(source_cases)

        cases: list[EvaluationCase] = []
        documents: list[CorpusDocument] = []
        gold_contents: set[str] = set()

        # 将每条 news1 转换成一篇金标准文档。
        for sequence, (source_index, source) in enumerate(
            selected_cases,
            start=1,
        ):
            case_id = f"crud-1doc-{sequence:06d}"
            document_key = f"{case_id}-news1"
            content = source["news1"].strip()

            if not content:
                raise ValueError(
                    f"news1 must not be blank: source_index={source_index}"
                )

            cases.append(
                EvaluationCase(
                    case_id=case_id,
                    source_record_id=str(source["ID"]),
                    source_index=source_index,
                    question=source["questions"].strip(),
                    reference_answer=source["answers"].strip(),
                    gold_document_keys=[document_key],
                )
            )

            documents.append(
                self._write_document(
                    document_key=document_key,
                    content=content,
                    is_gold=True,
                    case_id=case_id,
                    source_part=(
                        "crud_split/split_merged.json"
                        "#questanswer_1doc"
                    ),
                    source_line=None,
                )
            )
            gold_contents.add(self._normalize_text(content))

        # V2 优先选择与问题相似的错误文档，再用随机文档补齐数量。
        hard_negative_sources = self._sample_hard_negative_documents(
            cases=cases,
            excluded_contents=gold_contents,
        )
        hard_negative_contents = {
            self._normalize_text(content)
            for _, _, content in hard_negative_sources
        }
        random_negative_sources = self._sample_negative_documents(
            excluded_contents=gold_contents | hard_negative_contents,
            target_count=max(
                0,
                self._negative_count - len(hard_negative_sources),
            ),
        )
        negative_sources = hard_negative_sources + random_negative_sources

        for sequence, (source_part, source_line, content) in enumerate(
            negative_sources,
            start=1,
        ):
            documents.append(
                self._write_document(
                    document_key=f"crud-negative-{sequence:06d}",
                    content=content,
                    is_gold=False,
                    case_id=None,
                    source_part=source_part,
                    source_line=source_line,
                )
            )

        self._write_jsonl("cases.jsonl", cases)
        self._write_jsonl("corpus-manifest.jsonl", documents)

        summary = PreparedDatasetSummary(
            task_type=EvaluationTaskType.QUESTANSWER_1DOC,
            random_seed=self._random_seed,
            case_count=len(cases),
            gold_document_count=len(cases),
            negative_document_count=len(negative_sources),
            hard_negative_document_count=len(hard_negative_sources),
            total_document_count=len(documents),
        )

        (self._output_dir / "summary.json").write_text(
            summary.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return summary

    def _load_source_cases(self) -> list[dict]:
        """读取 split_merged.json 中的单文档问答。"""
        path = (
            self._crud_root
            / "data"
            / "crud_split"
            / "split_merged.json"
        )
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        cases = data.get("questanswer_1doc")
        if not isinstance(cases, list):
            raise ValueError("questanswer_1doc is missing or invalid")
        return cases

    def _select_cases(
        self,
        source_cases: list[dict],
    ) -> list[tuple[int, dict]]:
        """固定随机种子抽取 Case，并按原始位置排序。"""
        if self._case_count > len(source_cases):
            raise ValueError(
                f"case_count must be <= {len(source_cases)}"
            )

        indexed_cases = list(enumerate(source_cases))
        selected = self._random.sample(
            indexed_cases,
            self._case_count,
        )
        return sorted(selected, key=lambda item: item[0])

    def _sample_negative_documents(
        self,
        excluded_contents: set[str],
        target_count: int | None = None,
    ) -> list[tuple[str, int, str]]:
        """使用蓄水池算法抽取干扰文档，避免加载全部语料。"""
        expected_count = (
            self._negative_count
            if target_count is None
            else target_count
        )
        if expected_count == 0:
            return []

        reservoir: list[tuple[str, int, str]] = []
        eligible_count = 0

        for source_part, source_line, content in self._iter_corpus():
            normalized = self._normalize_text(content)

            if not normalized or normalized in excluded_contents:
                continue

            eligible_count += 1
            candidate = (source_part, source_line, content)

            if len(reservoir) < expected_count:
                reservoir.append(candidate)
                continue

            replace_index = self._random.randrange(eligible_count)
            if replace_index < expected_count:
                reservoir[replace_index] = candidate

        if len(reservoir) != expected_count:
            raise ValueError(
                "Not enough negative documents: "
                f"expected={expected_count}, "
                f"actual={len(reservoir)}"
            )
        return reservoir

    def _sample_hard_negative_documents(
        self,
        cases: list[EvaluationCase],
        excluded_contents: set[str],
    ) -> list[tuple[str, int, str]]:
        """按字符二元组相似度为每个问题选择难负样本文档。"""
        if self._hard_negative_per_case <= 0:
            return []

        question_grams = [
            self._character_grams(case.question)
            for case in cases
        ]
        heaps: list[list[tuple[float, str, int, str]]] = [
            [] for _ in cases
        ]

        for source_part, source_line, content in self._iter_corpus():
            normalized = self._normalize_text(content)
            if not normalized or normalized in excluded_contents:
                continue

            document_grams = self._character_grams(normalized)
            for index, query_grams in enumerate(question_grams):
                if not query_grams:
                    continue
                score = len(query_grams & document_grams) / len(query_grams)
                if score <= 0:
                    continue

                entry = (score, source_part, source_line, content)
                heap = heaps[index]
                if len(heap) < self._hard_negative_per_case:
                    heapq.heappush(heap, entry)
                elif score > heap[0][0]:
                    heapq.heapreplace(heap, entry)

        # 同一篇文档可能对多个问题都是难负样本，只生成一份文件。
        selected: list[tuple[str, int, str]] = []
        seen: set[str] = set()
        ranked_entries = sorted(
            (entry for heap in heaps for entry in heap),
            key=lambda entry: entry[0],
            reverse=True,
        )
        for _, source_part, source_line, content in ranked_entries:
            normalized = self._normalize_text(content)
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append((source_part, source_line, content))
            if len(selected) >= self._negative_count:
                break
        return selected

    def _iter_corpus(self) -> Iterable[tuple[str, int, str]]:
        """逐行读取正常语料，不读取 documents_hallu 文件。"""
        corpus_dir = self._crud_root / "data" / "80000_docs"
        part_files = sorted(
            corpus_dir.glob("documents_dup_part_*"),
            key=lambda path: self._natural_sort_key(path.name),
        )

        if not part_files:
            raise FileNotFoundError(
                f"No documents_dup_part files found: {corpus_dir}"
            )

        for part_file in part_files:
            with part_file.open("r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    content = line.strip()
                    if content:
                        yield part_file.name, line_number, content

    def _write_document(
        self,
        document_key: str,
        content: str,
        is_gold: bool,
        case_id: str | None,
        source_part: str,
        source_line: int | None,
    ) -> CorpusDocument:
        """写入一篇独立 TXT 文档并返回 Manifest。"""
        file_name = f"{document_key}.txt"
        relative_path = Path("documents") / file_name
        target = self._output_dir / relative_path
        target.write_text(content, encoding="utf-8")

        return CorpusDocument(
            document_key=document_key,
            file_name=file_name,
            relative_path=relative_path.as_posix(),
            sha256=hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            is_gold=is_gold,
            case_id=case_id,
            source_part=source_part,
            source_line=source_line,
        )

    def _write_jsonl(
        self,
        file_name: str,
        records: list[EvaluationCase | CorpusDocument],
    ) -> None:
        """按照一行一个 JSON 对象写入数据。"""
        target = self._output_dir / file_name
        with target.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(record.model_dump_json())
                file.write("\n")

    def _validate_paths(self) -> None:
        """检查输入目录和输出目录，避免覆盖已有数据。"""
        if not self._crud_root.is_dir():
            raise FileNotFoundError(
                f"CRUD-RAG root not found: {self._crud_root}"
            )

        if self._output_dir.exists() and any(
            self._output_dir.iterdir()
        ):
            raise FileExistsError(
                f"Output directory is not empty: {self._output_dir}"
            )

    def _create_output_directories(self) -> None:
        """创建输出目录和文档目录。"""
        (self._output_dir / "documents").mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """去除空白，用于排除重复文档。"""
        return re.sub(r"\s+", "", text)

    @classmethod
    def _character_grams(cls, text: str) -> set[str]:
        """提取字符二元组，用于无分词依赖的中文文本相似度排序。"""
        normalized = cls._normalize_text(text).lower()
        return {
            normalized[index:index + 2]
            for index in range(max(0, len(normalized) - 1))
        }

    @staticmethod
    def _natural_sort_key(value: str) -> list[int | str]:
        """让 part_2 排在 part_10 前面。"""
        return [
            int(part) if part.isdigit() else part
            for part in re.split(r"(\d+)", value)
        ]
