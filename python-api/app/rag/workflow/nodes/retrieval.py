"""知识库选择、混合检索、重排和上下文打包节点。"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.rag.workflow.dependencies import RetrievalDependencies
from app.rag.workflow.nodes.common import build_prepared, get_recorder
from app.rag.workflow.state import RagState


def make_select_knowledge_base_node(deps: RetrievalDependencies):
    """创建知识库选择节点；不明确时转入澄清。"""
    def select_knowledge_base_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        request = state["request"]
        resolved_query = state["resolved_query"]
        route_decision = state["route_decision"]

        with deps.trace_node(
            "KNOWLEDGE_BASE_SELECT",
            recorder=recorder,
        ) as node:
            selection = deps.select_knowledge_base(
                tenant_id=request.tenant_id or 0,
                user_id=request.user_id or 0,
                preferred_knowledge_base_id=request.knowledge_base_id,
                query=resolved_query.standalone_query,
                domain=route_decision.domain.value,
            )
            if node is not None:
                node.set_output({
                    "knowledgeBaseId": selection.knowledge_base_id,
                    "selectionType": selection.selection_type,
                    "needClarification": selection.need_clarification,
                })

        result: dict[str, Any] = {
            "knowledge_base_selection": selection,
        }
        if selection.need_clarification:
            result["clarification_answer"] = (
                deps.build_clarification_answer(selection)
            )
        return result

    return select_knowledge_base_node


def make_rewrite_retrieval_query_node(deps: RetrievalDependencies):
    """创建面向检索的查询改写节点。"""
    def rewrite_retrieval_query_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)

        with deps.trace_node(
            "RETRIEVAL_QUERY_REWRITE",
            recorder=recorder,
        ) as node:
            retrieval_query = deps.rewrite_retrieval_query(
                state["resolved_query"].standalone_query
            )
            if node is not None:
                node.set_output({
                    "semanticQuery": (
                        retrieval_query.semantic_query[:1000]
                    ),
                    "keywords": retrieval_query.keywords,
                })

        return {"retrieval_query": retrieval_query}

    return rewrite_retrieval_query_node


def make_retrieve_hybrid_node(deps: RetrievalDependencies):
    """创建向量与关键词混合检索节点。"""
    def retrieve_hybrid_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        request = state["request"]
        retrieval_query = state["retrieval_query"]
        selection = state["knowledge_base_selection"]

        with deps.trace_node(
            "HYBRID_RETRIEVE",
            recorder=recorder,
        ) as node:
            documents, stats = deps.retrieve_documents(
                semantic_query=retrieval_query.semantic_query,
                keywords=retrieval_query.keywords,
                tenant_id=request.tenant_id or 0,
                knowledge_base_id=selection.knowledge_base_id,
                alternative_queries=(
                    retrieval_query.alternative_queries
                    if deps.settings.retrieval_multi_query_enabled
                    else []
                ),
            )
            if node is not None:
                node.set_output({
                    "candidateCount": len(documents),
                    "vectorCount": stats.vector_merged_count,
                    "keywordCount": stats.keyword_count,
                    "multiQueryCount": stats.multi_query_count,
                    "fusedCount": stats.fused_count,
                })

        return {"retrieved_documents": documents}

    return retrieve_hybrid_node


def make_rerank_documents_node(deps: RetrievalDependencies):
    """创建检索结果精排节点。"""
    def rerank_documents_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        documents = state["retrieved_documents"]

        with deps.trace_node(
            "RERANK",
            recorder=recorder,
        ) as node:
            reranked_documents = deps.rerank_documents(
                state["resolved_query"].standalone_query,
                documents,
            )
            if node is not None:
                node.set_output({
                    "inputCount": len(documents),
                    "resultCount": len(reranked_documents),
                })

        return {"reranked_documents": reranked_documents}

    return rerank_documents_node


def make_pack_context_node(deps: RetrievalDependencies):
    """创建上下文预算打包、引用构建和结果组装节点。"""
    def pack_context_node(
        state: RagState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        recorder = get_recorder(config)
        retrieved_documents = state["retrieved_documents"]
        reranked_documents = state["reranked_documents"]

        with deps.trace_node(
            "CONTEXT_PACK",
            recorder=recorder,
        ) as node:
            packed_context = deps.pack_documents(reranked_documents)
            citations = deps.build_citations(
                packed_context.documents
            )
            if node is not None:
                node.set_output({
                    "documentCount": len(packed_context.documents),
                    "totalChars": packed_context.total_chars,
                    "truncated": packed_context.truncated,
                })

        # RagPrepared 是生成前工作流对其他模块的唯一输出。
        prepared = build_prepared(
            deps.settings,
            state,
            intent=state["route_decision"].intent.value,
            need_rag=True,
            knowledge_base_id=(
                state["knowledge_base_selection"].knowledge_base_id
            ),
            context=packed_context.text,
            documents=packed_context.documents,
            citations=citations,
            candidate_count=len(retrieved_documents),
            rerank_count=len(reranked_documents),
            context_document_count=len(packed_context.documents),
            no_evidence=not packed_context.text.strip(),
        )
        return {
            "packed_context": packed_context,
            "prepared": prepared,
        }

    return pack_context_node
