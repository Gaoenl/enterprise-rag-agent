"""RAG Trace 运行时记录器。"""
from datetime import datetime, timezone
from time import perf_counter
from tkinter.font import names
from types import TracebackType
from typing import Any

from app.schemas.trace_schema import TraceNode, TraceNodeStatus, RagTraceData, TraceStatus, TokenUsage


def utc_now()->datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)

class TraceNodeContext:
    """单个 Trace 节点的上下文管理器。"""

    def __init__(
            self,
            recorder: "TraceRecorder",
            name: str,
            input_summary: dict[str, Any] | None,
    ) -> None:
        """创建尚未开始的 Trace 节点。"""
        self._recorder = recorder
        self._name = name
        self._input_summary = input_summary or {}
        self._started_counter: float | None = None
        self.node: TraceNode | None = None

    def __enter__(self) -> "TraceNodeContext":
        """开始记录节点。"""
        self._started_counter = perf_counter()
        self.node = TraceNode(
            name=self._name,
            status=TraceNodeStatus.RUNNING,
            started_at=utc_now(),
            input_summary=self._input_summary
        )
        self._recorder.trace.nodes.append(self.node)
        return self

    def set_output(
            self,
            output_summary: dict[str, Any],
    ) -> None:
        """设置节点输出摘要。"""
        if self.node is not None:
            self.node.output_summary = output_summary

    def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: TracebackType | None,
    ) -> bool:
        """完成节点并记录成功或异常状态。"""
        if self.node is None:
            return False

        finished_at = utc_now()
        self.node.finished_at = finished_at

        if self._started_counter is not None:
            self.node.latency_ms = int(
                (perf_counter() - self._started_counter)
                * 1000
            )

        if exception is None:
            self.node.status = TraceNodeStatus.SUCCESS
        else:
            self.node.status = TraceNodeStatus.FAILED
            self.node.error_message = str(exception)[:2000]

        # 返回 False，表示异常继续向外传播。
        return False
class TraceRecorder:
    """记录一次完整 Chat/RAG 请求。"""

    def __init__(
            self,
            trace_id: int,
            request_id: str | None,
            input_summary: dict[str, Any],
    ) -> None:
        """初始化 Trace 根对象。"""
        self._started_counter = perf_counter()

        self.trace = RagTraceData(
            trace_id=trace_id,
            request_id=request_id,
            status=TraceStatus.RUNNING,
            started_at=utc_now(),
            input=input_summary,
        )

    def node(
            self,
            name: str,
            input_summary: dict[str, Any] | None = None,
    ) -> TraceNodeContext:
        """创建一个节点上下文。"""
        return TraceNodeContext(
            recorder=self,
            name=name,
            input_summary=input_summary,
        )

    def skip(
            self,
            name: str,
            reason: str | None = None,
            input_summary: dict[str, Any] | None = None,
    ) -> None:
        """记录一个被跳过的节点（SKIPPED）。

        用于流程中的短路分支：节点本应执行，但因澄清、无依据、
        非 RAG 等决策被跳过，便于 Trace 页展示完整决策链路。
        """
        now = utc_now()
        self.trace.nodes.append(
            TraceNode(
                name=name,
                status=TraceNodeStatus.SKIPPED,
                started_at=now,
                finished_at=now,
                input_summary=input_summary or {},
                error_message=reason,
            )
        )

    def mark_degraded(self, reason: str) -> None:
        """记录发生过可恢复的降级。"""
        if reason not in self.trace.degraded_reasons:
            self.trace.degraded_reasons.append(reason)

        if self.trace.status != TraceStatus.FAILED:
            self.trace.status = TraceStatus.DEGRADED

    def finish(
            self,
            output_summary: dict[str, Any],
            token_usage: TokenUsage | None = None,
    ) -> RagTraceData:
        """成功完成 Trace。"""
        self.trace.finished_at = utc_now()
        self.trace.latency_ms = int(
            (perf_counter() - self._started_counter)
            * 1000
        )
        self.trace.output = output_summary

        if token_usage is not None:
            self.trace.token_usage = token_usage

        # 发生过降级时保留 DEGRADED。
        if self.trace.status != TraceStatus.DEGRADED:
            self.trace.status = TraceStatus.SUCCESS

        return self.trace

    def fail(
            self,
            exception: BaseException,
    ) -> RagTraceData:
        """将整条 Trace 标记为失败。"""
        self.trace.finished_at = utc_now()
        self.trace.latency_ms = int(
            (perf_counter() - self._started_counter)
            * 1000
        )
        self.trace.status = TraceStatus.FAILED
        self.trace.error_message = str(exception)[:2000]

        return self.trace

