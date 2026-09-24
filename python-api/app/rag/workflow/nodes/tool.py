"""工具校验和执行节点。"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.rag.workflow.dependencies import ToolDependencies
from app.rag.workflow.nodes.common import build_prepared, get_recorder
from app.rag.workflow.state import RagState


def make_prepare_tool_node(deps: ToolDependencies):
    """创建工具节点；工具不可用或执行失败时转入澄清。"""
    def prepare_tool_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        request = state["request"]
        route_decision = state["route_decision"]
        tool = route_decision.tool

        if (
            not request.tool_enabled
            or tool is None
            or not deps.is_tool_registered(tool.tool)
        ):
            return {
                "clarification_answer": (
                    "当前请求需要调用工具，但该工具尚未开通，"
                    "请稍后再试或换一种问法。"
                )
            }

        with deps.trace_node(
            "TOOL_EXECUTE",
            {
                "tool": tool.tool,
                "input": str(tool.tool_input)[:500],
            },
            recorder=recorder,
        ) as node:
            try:
                result = deps.execute_tool(
                    tool.tool,
                    tool.tool_input,
                )
            except Exception as exception:
                if node is not None:
                    node.set_output(
                        {"error": str(exception)[:500]}
                    )
                return {
                    "clarification_answer": (
                        f"工具执行失败：{exception}，"
                        "请稍后再试或换一种问法。"
                    )
                }

            if node is not None:
                node.set_output({"resultChars": len(result)})

        return {
            "tool_result": result,
            "prepared": build_prepared(
                deps.settings,
                state,
                intent=route_decision.intent.value,
                need_rag=False,
                tool_result=result,
            ),
        }

    return prepare_tool_node
