import logging
from sqlalchemy import insert, select, text, update
from app.config import Settings, get_settings
from app.memory.models import ConversationContext
from app.memory.redis_cache import RedisConversationCache
from fastapi import HTTPException

from app.rag.schemas.routing_schema import RouteDecision
from app.rag.trace.trace_recorder import TraceRecorder
from app.schemas.chat_schema import ChatHistoryMessage

logger = logging.getLogger(__name__)

class ConversationMemory:
    HISTORY_LIMIT = 10
    SUMMARY_LOAD_PAIRS = 15
    COUNT_THRESHOLD = 15
    TOKEN_THRESHOLD = 2000
    KEEP_RECENT_PAIRS = 5

    def __init__(
        self,
        database,
        cache: RedisConversationCache | None = None,
        settings: Settings | None = None,
    ):
        self.db = database
        self._settings = settings or get_settings()
        self.cache = (
            cache
            if cache is not None
            else (
                RedisConversationCache(self._settings)
                if self._settings.redis_enabled
                else None
            )
        )

    def close(self):
        self.db.close()

    def _require_conversation(self, session, request):
        table = self.db.conversations
        row = session.execute(
            select(table).where(
                table.c.id == request.conversation_id,
                table.c.tenant_id == request.tenant_id,
                table.c.user_id == request.user_id,
                table.c.deleted.is_(False),
            )
        ).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, "会话不存在或无权访问")
        return row

    def _load_pairs(self, session, conversation, limit=None):
        """读取尚未被摘要覆盖的完整问答，排除失败的孤立用户消息。"""
        messages = self.db.messages
        users = messages.alias("user_message")
        assistants = messages.alias("assistant_message")
        stmt = (
            select(
                assistants.c.id.label("assistant_id"),
                users.c.content.label("question"),
                assistants.c.content.label("answer"),
            )
            .select_from(
                assistants.join(
                    users,
                    (assistants.c.parent_message_id == users.c.id)
                    & (assistants.c.tenant_id == users.c.tenant_id)
                    & (
                            assistants.c.conversation_id
                            == users.c.conversation_id
                    ),
                )
            )
            .where(
                assistants.c.conversation_id == conversation["id"],
                assistants.c.tenant_id == conversation["tenant_id"],
                assistants.c.role == "ASSISTANT",
                users.c.role == "USER",
                assistants.c.deleted.is_(False),
                users.c.deleted.is_(False),
            )
            .order_by(assistants.c.id.desc())
        )

        watermark = conversation["last_summary_message_id"]
        if watermark is not None:
            stmt = stmt.where(assistants.c.id > watermark)

        if limit is not None:
            stmt = stmt.limit(limit)

        rows = list(session.execute(stmt).mappings())
        rows.reverse()
        return rows

    def begin(self, request) -> ConversationContext:
        conversations = self.db.conversations
        messages = self.db.messages
        traces = self.db.traces

        # 会话、用户消息、RUNNING trace 在同一个短事务里创建。
        with self.db.sessions.begin() as session:
            if request.conversation_id is None:
                conversation = session.execute(
                    insert(conversations)
                    .values(
                        tenant_id=request.tenant_id,
                        user_id=request.user_id,
                        knowledge_base_id=request.knowledge_base_id,
                        title=request.question.strip()[:30],
                        channel="WEB",
                    )
                    .returning(conversations)
                ).mappings().one()
            else:
                conversation = self._require_conversation(
                    session, request
                )

            conversation_id = conversation["id"]

            # 仅覆盖这个短事务，不在模型生成期间持有数据库锁。
            # 所有 Python 聊天入口统一使用相同锁规则。
            acquired = session.scalar(
                text(
                    "SELECT pg_try_advisory_xact_lock(:id)"
                ),
                {"id": conversation_id},
            )
            if not acquired:
                raise HTTPException(409, "会话正在处理其他请求")

            running = session.scalar(
                select(traces.c.id)
                .where(
                    traces.c.tenant_id == request.tenant_id,
                    traces.c.conversation_id == conversation_id,
                    traces.c.status == "RUNNING",
                )
                .limit(1)
            )
            if running is not None:
                raise HTTPException(409, "请等待本轮回答完成")

            cached_history = (
                self.cache.get_messages(
                    conversation_id,
                    self.HISTORY_LIMIT,
                )
                if self.cache is not None
                else []
            )

            # 历史在保存当前问题之前读取，避免问题重复进入上下文。
            if cached_history:
                history = [
                    ChatHistoryMessage(
                        role=item["role"],
                        content=item["content"],
                    )
                    for item in cached_history
                ]
            else:
                pairs = self._load_pairs(
                    session,
                    conversation,
                    limit=self.HISTORY_LIMIT,
                )
                history = []
                for pair in pairs:
                    history.extend([
                        ChatHistoryMessage(
                            role="USER", content=pair["question"]
                        ),
                        ChatHistoryMessage(
                            role="ASSISTANT", content=pair["answer"]
                        ),
                    ])
                if self.cache is not None:
                    self.cache.replace_messages(
                        conversation_id,
                        [
                            {
                                "role": item.role,
                                "content": item.content,
                            }
                            for item in history
                        ],
                    )

            user_message_id = session.scalar(
                insert(messages)
                .values(
                    tenant_id=request.tenant_id,
                    conversation_id=conversation_id,
                    role="USER",
                    content=request.question,
                    trace_id=request.trace_id,
                )
                .returning(messages.c.id)
            )

            recorder = TraceRecorder(
                trace_id=request.trace_id,
                request_id=request.request_id,
                input_summary={
                    "tenantId": request.tenant_id,
                    "userId": request.user_id,
                    "conversationId": conversation_id,
                    "userMessageId": user_message_id,
                    "knowledgeBaseId": request.knowledge_base_id,
                    "question": request.question[:1000],
                },
            )

            session.execute(
                insert(traces).values(
                    id=request.trace_id,
                    tenant_id=request.tenant_id,
                    conversation_id=conversation_id,
                    trace_type="CHAT_QA",
                    request_id=request.request_id,
                    input=recorder.trace.input,
                    status="RUNNING",
                    started_at=recorder.trace.started_at,
                )
            )

            last_route = conversation["last_route"]
            cached_summary = (
                self.cache.get_summary(conversation_id)
                if self.cache is not None
                else None
            )

            context = ConversationContext(
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                trace_id=request.trace_id,
                history=history,
                summary=(
                    cached_summary
                    or conversation["summary"]
                    or ""
                ),
                last_route=(
                    RouteDecision.model_validate(last_route)
                    if last_route else None
                ),
                trace=recorder.trace,
            )

        return context

    @staticmethod
    def _trace_values(trace):
        return {
            "status": trace.status.value,
            "input": trace.input,
            "output": trace.output,
            "nodes": [
                node.model_dump(by_alias=True, mode="json")
                for node in trace.nodes
            ],
            "token_usage": trace.token_usage.model_dump(
                by_alias=True, mode="json"
            ),
            "degraded_reasons": trace.degraded_reasons,
            "latency_ms": trace.latency_ms,
            "started_at": trace.started_at,
            "finished_at": trace.finished_at,
            "error_message": trace.error_message,
        }

    def complete(self, context, data):
        conversations = self.db.conversations
        messages = self.db.messages
        traces = self.db.traces

        if data.trace is None:
            raise ValueError("最终结果缺少 trace")
        if data.trace_id != context.trace_id:
            raise ValueError("traceId 不一致")

        with self.db.sessions.begin() as session:
            # 锁住当前执行记录，重复 final 不会重复插入助手消息。
            row = session.execute(
                select(traces).where(
                    traces.c.id == context.trace_id,
                    traces.c.tenant_id == context.tenant_id,
                    traces.c.conversation_id == context.conversation_id,
                ).with_for_update()
            ).mappings().one()

            if row["status"] in ("SUCCESS", "DEGRADED"):
                return

            if row["status"] != "RUNNING":
                raise RuntimeError("当前请求已结束，不能保存回答")

            assistant_id = session.scalar(
                insert(messages)
                .values(
                    tenant_id=context.tenant_id,
                    conversation_id=context.conversation_id,
                    parent_message_id=context.user_message_id,
                    role="ASSISTANT",
                    content=data.answer,
                    citations=data.citations,
                    token_usage=data.token_usage.model_dump(
                        by_alias=True, mode="json"
                    ),
                    trace_id=context.trace_id,
                )
                .returning(messages.c.id)
            )

            values = {}
            if data.knowledge_base_id is not None:
                values["knowledge_base_id"] = data.knowledge_base_id
            if data.route is not None:
                values["last_route"] = data.route.model_dump(
                    mode="json", by_alias=True
                )

            if values:
                session.execute(
                    update(conversations)
                    .where(
                        conversations.c.id == context.conversation_id,
                        conversations.c.tenant_id == context.tenant_id,
                        conversations.c.user_id == context.user_id,
                        conversations.c.deleted.is_(False),
                    )
                    .values(**values)
                )

            session.execute(
                update(traces)
                .where(traces.c.id == context.trace_id)
                .values(
                    message_id=assistant_id,
                    **self._trace_values(data.trace),
                )
            )

        if self.cache is not None:
            self.cache.append_messages(
                context.conversation_id,
                [
                    {
                        "role": "USER",
                        "content": data.question,
                    },
                    {
                        "role": "ASSISTANT",
                        "content": data.answer,
                    },
                ],
                self.HISTORY_LIMIT,
            )

    def fail(self, context, trace):
        """使用新的短事务保留 Python 已经执行的节点。"""
        table = self.db.traces

        with self.db.sessions.begin() as session:
            session.execute(
                update(table)
                .where(
                    table.c.id == context.trace_id,
                    table.c.tenant_id == context.tenant_id,
                    table.c.status == "RUNNING",
                )
                .values(**self._trace_values(trace))
            )
    def summarize_if_needed(self, context, summary_service):
        from app.schemas.conversation_summary_schema import (
            SummarizeRequest,
            SummaryMessage,
        )

        conversations = self.db.conversations

        # 读取数据后关闭事务，再调用模型。
        with self.db.sessions() as session:
            conversation = session.execute(
                select(conversations).where(
                    conversations.c.id == context.conversation_id,
                    conversations.c.tenant_id == context.tenant_id,
                    conversations.c.user_id == context.user_id,
                    conversations.c.deleted.is_(False),
                )
            ).mappings().one_or_none()

            if conversation is None:
                return

            pairs = self._load_pairs(
                session,
                conversation,
                limit=self.SUMMARY_LOAD_PAIRS,
            )

        # 保留最近五轮，即十条原文消息；不截断问答配对。
        older_pairs = pairs[:-self.KEEP_RECENT_PAIRS]
        if not older_pairs:
            return

        message_count = len(pairs) * 2
        estimated_tokens = sum(
            (len(p["question"]) + len(p["answer"]) + 1) // 2
            for p in pairs
        )

        if (
            message_count < self.COUNT_THRESHOLD
            and estimated_tokens < self.TOKEN_THRESHOLD
        ):
            return

        items = []
        for pair in older_pairs:
            items.extend([
                SummaryMessage(
                    role="USER", content=pair["question"]
                ),
                SummaryMessage(
                    role="ASSISTANT", content=pair["answer"]
                ),
            ])

        summary = summary_service.summarize(
            SummarizeRequest(
                messages=items,
                old_summary=conversation["summary"] or "",
            )
        )
        if not summary.strip():
            return

        old_watermark = conversation["last_summary_message_id"]
        new_watermark = older_pairs[-1]["assistant_id"]

        # 防止两个摘要任务互相覆盖；正确处理初始 NULL。
        with self.db.sessions.begin() as session:
            result = session.execute(
                update(conversations)
                .where(
                    conversations.c.id == context.conversation_id,
                    conversations.c.tenant_id == context.tenant_id,
                    conversations.c.user_id == context.user_id,
                    conversations.c.deleted.is_(False),
                    conversations.c.last_summary_message_id
                    .is_not_distinct_from(old_watermark),
                )
                .values(
                    summary=summary,
                    last_summary_message_id=new_watermark,
                )
            )
            updated = result.rowcount > 0

        if updated and self.cache is not None:
            self.cache.save_summary(
                context.conversation_id,
                summary,
            )
            recent_pairs = pairs[-self.KEEP_RECENT_PAIRS:]
            self.cache.replace_messages(
                context.conversation_id,
                [
                    message
                    for pair in recent_pairs
                    for message in (
                        {
                            "role": "USER",
                            "content": pair["question"],
                        },
                        {
                            "role": "ASSISTANT",
                            "content": pair["answer"],
                        },
                    )
                ],
            )
