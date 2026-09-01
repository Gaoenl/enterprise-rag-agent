"""AnswerPostProcessor unit tests."""

from langchain_core.documents import Document

from app.rag.postprocess.answer_postprocessor import AnswerPostProcessor
from app.schemas.answer_schema import AnswerStatus


def create_document(citation_index: int) -> Document:
    """Create one packed document with a stable citation index."""
    return Document(
        page_content=f"source {citation_index} content",
        metadata={
            "chunk_id": citation_index,
            "citation_index": citation_index,
        },
    )


def test_general_answer_does_not_require_citations() -> None:
    processor = AnswerPostProcessor()

    result = processor.process(
        answer="Hello, how can I help?",
        documents=[],
        rag_mode=False,
    )

    assert result.answer_status == AnswerStatus.GENERAL
    assert result.used_citation_indexes == []
    assert result.invalid_citation_indexes == []


def test_valid_citations_are_preserved() -> None:
    processor = AnswerPostProcessor()

    result = processor.process(
        answer=(
            "The expense requires approval.[来源 1]"
            " See the policy for details.[来源 2]"
        ),
        documents=[
            create_document(1),
            create_document(2),
        ],
        rag_mode=True,
    )

    assert "[来源 1]" in result.answer
    assert "[来源 2]" in result.answer
    assert result.used_citation_indexes == [1, 2]
    assert result.invalid_citation_indexes == []
    assert result.answer_status == AnswerStatus.ANSWERED


def test_invalid_citation_is_removed_and_reported() -> None:
    processor = AnswerPostProcessor()

    result = processor.process(
        answer=(
            "Supported statement.[来源 1]"
            " Unsupported statement.[来源 9]"
        ),
        documents=[
            create_document(1),
            create_document(2),
        ],
        rag_mode=True,
    )

    assert "[来源 1]" in result.answer
    assert "[来源 9]" not in result.answer
    assert result.used_citation_indexes == [1]
    assert result.invalid_citation_indexes == [9]


def test_duplicate_citation_is_recorded_once() -> None:
    processor = AnswerPostProcessor()

    result = processor.process(
        answer=(
            "First statement.[来源 1]"
            " Second statement.[来源 1]"
        ),
        documents=[
            create_document(1),
        ],
        rag_mode=True,
    )

    assert result.answer.count("[来源 1]") == 2
    assert result.used_citation_indexes == [1]


def test_no_evidence_returns_no_evidence_status() -> None:
    processor = AnswerPostProcessor()

    result = processor.process(
        answer="No sufficient evidence was found.",
        documents=[],
        rag_mode=True,
        no_evidence=True,
    )

    assert result.answer_status == AnswerStatus.NO_EVIDENCE
    assert result.used_citation_indexes == []
    assert result.invalid_citation_indexes == []


def test_whitespace_in_citation_is_normalized() -> None:
    processor = AnswerPostProcessor()

    result = processor.process(
        answer="Supported statement.[来源   2]",
        documents=[
            create_document(2),
        ],
        rag_mode=True,
    )

    assert result.answer == "Supported statement.[来源 2]"
    assert result.used_citation_indexes == [2]

