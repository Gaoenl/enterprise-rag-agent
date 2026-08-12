-- V17: 会话摘要压缩
ALTER TABLE chat_conversation
    ADD COLUMN IF NOT EXISTS summary TEXT,
    ADD COLUMN IF NOT EXISTS last_summary_message_id BIGINT;