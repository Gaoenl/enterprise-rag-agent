"""Redis working-memory cache for chat conversations."""

import json
import logging

from redis import Redis
from redis.exceptions import RedisError

from app.config import Settings

logger = logging.getLogger(__name__)


class RedisConversationCache:
    """Store recent complete turns and summaries in Redis."""

    TTL_SECONDS = 86400

    def __init__(self, settings: Settings) -> None:
        self._client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    @staticmethod
    def _messages_key(conversation_id: int) -> str:
        return f"wm:{conversation_id}"

    @staticmethod
    def _summary_key(conversation_id: int) -> str:
        return f"wm:{conversation_id}:summary"

    def get_messages(
        self,
        conversation_id: int,
        limit: int,
    ) -> list[dict[str, str]]:
        try:
            raw_items = self._client.lrange(
                self._messages_key(conversation_id),
                -limit,
                -1,
            )
        except RedisError:
            logger.warning(
                "读取 Redis 会话工作记忆失败, conversation_id=%s",
                conversation_id,
                exc_info=True,
            )
            return []

        messages: list[dict[str, str]] = []
        for raw in raw_items:
            try:
                item = json.loads(raw)
            except (TypeError, ValueError):
                logger.warning(
                    "忽略损坏的 Redis 会话消息, conversation_id=%s",
                    conversation_id,
                )
                continue
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                messages.append({"role": role, "content": content})
        return messages

    def replace_messages(
        self,
        conversation_id: int,
        messages: list[dict[str, str]],
    ) -> None:
        key = self._messages_key(conversation_id)
        try:
            pipe = self._client.pipeline(transaction=False)
            pipe.delete(key)
            if messages:
                pipe.rpush(
                    key,
                    *[
                        json.dumps(
                            item,
                            ensure_ascii=False,
                        )
                        for item in messages
                    ],
                )
                pipe.expire(key, self.TTL_SECONDS)
            pipe.execute()
        except RedisError:
            logger.warning(
                "写入 Redis 会话工作记忆失败, conversation_id=%s",
                conversation_id,
                exc_info=True,
            )

    def append_messages(
        self,
        conversation_id: int,
        messages: list[dict[str, str]],
        limit: int,
    ) -> None:
        if not messages:
            return

        key = self._messages_key(conversation_id)
        try:
            pipe = self._client.pipeline(transaction=False)
            pipe.rpush(
                key,
                *[
                    json.dumps(item, ensure_ascii=False)
                    for item in messages
                ],
            )
            pipe.ltrim(key, -limit, -1)
            pipe.expire(key, self.TTL_SECONDS)
            pipe.execute()
        except RedisError:
            logger.warning(
                "追加 Redis 会话工作记忆失败, conversation_id=%s",
                conversation_id,
                exc_info=True,
            )

    def get_summary(self, conversation_id: int) -> str | None:
        try:
            return self._client.get(
                self._summary_key(conversation_id)
            )
        except RedisError:
            logger.warning(
                "读取 Redis 会话摘要失败, conversation_id=%s",
                conversation_id,
                exc_info=True,
            )
            return None

    def save_summary(
        self,
        conversation_id: int,
        summary: str,
    ) -> None:
        try:
            self._client.set(
                self._summary_key(conversation_id),
                summary,
                ex=self.TTL_SECONDS,
            )
        except RedisError:
            logger.warning(
                "写入 Redis 会话摘要失败, conversation_id=%s",
                conversation_id,
                exc_info=True,
            )

    def delete(self, conversation_id: int) -> None:
        try:
            self._client.delete(
                self._messages_key(conversation_id),
                self._summary_key(conversation_id),
            )
        except RedisError:
            logger.warning(
                "删除 Redis 会话记忆失败, conversation_id=%s",
                conversation_id,
                exc_info=True,
            )
