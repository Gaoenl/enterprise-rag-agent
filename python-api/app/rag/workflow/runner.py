"""LangGraph RAG 工作流的公开运行入口。"""

from langchain_core.runnables import RunnableConfig

from app.rag.schemas.query_schema import RagPrepared, RagQuery
from app.rag.tools.registry import execute, is_registered
from app.rag.trace.trace_recorder import TraceRecorder
from app.rag.workflow.dependencies import (
    RagWorkflowDependencies,
    RetrievalDependencies,
    RoutingDependencies,
    ToolDependencies,
)
from app.rag.workflow.graph import build_prepare_graph


class RagWorkflow:
    """运行生成前图编排；LLM 生成仍由 RagEngine 负责。"""

    def __init__(self, dependencies: RagWorkflowDependencies) -> None:
        self._dependencies = dependencies
        self._graph = build_prepare_graph(dependencies)

    @classmethod
    def from_engine(cls, engine) -> "RagWorkflow":
        """把 RagEngine 能力适配为工作流依赖。

        这是工作流访问引擎私有能力的唯一位置，节点本身不感知 Engine。
        """
        settings = engine._settings
        return cls(
            RagWorkflowDependencies(
                routing=RoutingDependencies(
                    settings=settings,
                    trace_node=engine._node,
                    resolve_query=lambda request: (
                        engine._query_resolver.resolve(
                            question=request.question,
                            history=request.history,
                        )
                    ),
                    route_intent=engine._resolve_route,
                    skip_retrieval_stage=(
                        engine._skip_retrieval_stage
                    ),
                ),
                retrieval=RetrievalDependencies(
                    settings=settings,
                    trace_node=engine._node,
                    select_knowledge_base=(
                        engine._knowledge_base_selector.select
                    ),
                    rewrite_retrieval_query=(
                        engine._retrieval_query_rewriter.rewrite
                    ),
                    retrieve_documents=(
                        engine._retriever.retrieve_with_stats
                    ),
                    rerank_documents=lambda query, documents: (
                        engine._rerank_service.rerank(
                            query=query,
                            documents=documents,
                        )
                    ),
                    pack_documents=engine._context_packer.pack,
                    build_citations=engine._build_citations,
                    build_clarification_answer=(
                        engine._build_clarification_answer
                    ),
                ),
                tool=ToolDependencies(
                    settings=settings,
                    trace_node=engine._node,
                    is_tool_registered=is_registered,
                    execute_tool=execute,
                ),
            )
        )

    def prepare(
        self,
        request: RagQuery,
        recorder: TraceRecorder | None = None,
    ) -> RagPrepared:
        """执行工作流并返回 LLM 生成前的准备结果。"""
        state = self._graph.invoke(
            {"request": request},
            config=RunnableConfig(
                configurable={"recorder": recorder}
            ),
        )
        prepared = state.get("prepared")
        if prepared is None:
            raise RuntimeError("RAG graph completed without prepared result")
        return prepared
