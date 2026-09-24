-- V19__chat_memory_python_ids.sql
-- 仅用于聊天写入所有权切换；保留全部历史 ID。

LOCK TABLE chat_conversation, chat_message
    IN ACCESS EXCLUSIVE MODE;

CREATE SEQUENCE chat_conversation_id_seq AS BIGINT;
CREATE SEQUENCE chat_message_id_seq AS BIGINT;

SELECT setval(
               'chat_conversation_id_seq',
               COALESCE((SELECT MAX(id) FROM chat_conversation), 0) + 1,
               false
       );

SELECT setval(
               'chat_message_id_seq',
               COALESCE((SELECT MAX(id) FROM chat_message), 0) + 1,
               false
       );

ALTER SEQUENCE chat_conversation_id_seq
    OWNED BY chat_conversation.id;

ALTER SEQUENCE chat_message_id_seq
    OWNED BY chat_message.id;

ALTER TABLE chat_conversation
    ALTER COLUMN id SET DEFAULT
        nextval('chat_conversation_id_seq');

ALTER TABLE chat_message
    ALTER COLUMN id SET DEFAULT
        nextval('chat_message_id_seq');

-- 用于快速判断同一会话是否正在执行问答。
CREATE INDEX idx_rag_trace_running_conversation
    ON rag_trace (tenant_id, conversation_id)
    WHERE status = 'RUNNING';