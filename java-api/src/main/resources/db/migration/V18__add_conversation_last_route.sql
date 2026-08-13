-- 会话表记录上一轮意图路由决策，供 Python 多轮继承（无状态化）。
ALTER TABLE chat_conversation
    ADD COLUMN IF NOT EXISTS last_route JSONB;
