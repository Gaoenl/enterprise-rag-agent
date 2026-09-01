"""向量检索和关键词检索的共享并行执行器。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from sqlalchemy.testing import future

from app.rag.schemas.retrieval_schema import RetrievalCandidate


@dataclass
class RetrievalBranchResult:
    """单路检索执行结果。"""

    candidates: list[RetrievalCandidate]
    elapsed_millis: int
    error: Exception | None = None


# 多个请求共享线程池，避免每次检索都创建和销毁线程。
_executor = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="rag-retrieval",
)


def run_parallel_retrieval(
    vector_call: Callable[[], list[RetrievalCandidate]],
    keyword_call: Callable[[], list[RetrievalCandidate]],
) -> tuple[RetrievalBranchResult, RetrievalBranchResult]:
    """兼容原两路接口：并行执行向量与关键词检索。"""
    vector, keyword = run_parallel_calls(
        [vector_call, keyword_call]
    )
    return vector, keyword
def run_parallel_calls(
    calls: list[Callable[[], list[RetrievalCandidate]]],
) -> list[RetrievalBranchResult]:
    """并行执行任意数量检索调用，按传入顺序返回结果。"""
    futures = [
        _executor.submit(_execute_safely, call)
        for call in calls
    ]
    return [future.result() for future in futures]

def _execute_safely(
    retrieval_call: Callable[[], list[RetrievalCandidate]],
) -> RetrievalBranchResult:
    """捕获单路异常并记录准确耗时。"""
    started = perf_counter()

    try:
        candidates = retrieval_call()

        return RetrievalBranchResult(
            candidates=candidates,
            elapsed_millis=_elapsed_millis(started),
        )
    except Exception as exception:
        return RetrievalBranchResult(
            candidates=[],
            elapsed_millis=_elapsed_millis(started),
            error=exception,
        )


def shutdown_retrieval_executor() -> None:
    """应用停止时关闭检索线程池。"""
    _executor.shutdown(
        wait=True,
        cancel_futures=True,
    )


def _elapsed_millis(started: float) -> int:
    return round((perf_counter() - started) * 1000)