# Step 15：多轮会话历史与持久化

## 1. 目标

在基础问答上增加正式会话和消息历史：

```text
Frontend
  -> Java 创建或读取会话
  -> Java 查询最近历史消息
  -> Java 保存用户消息
  -> Java 将历史传给 Python
  -> Python 结合历史生成回答
  -> Java 保存助手消息
```

## 2. 历史数据的所有权

正式会话历史由 Java 和 PostgreSQL 管理：

- `chat_conversation` 保存会话。
- `chat_message` 保存 USER 和 ASSISTANT 消息。
- Java 负责租户隔离、用户归属、分页查询和软删除。
- Python 只消费 Java 传入的最近历史，不作为正式历史的数据源。

这样可以避免 Python 进程重启导致历史丢失，并确保审计、权限和数据一致性由业务后端控制。

## 3. 请求结构

```json
{
  "question": "它有哪些优势？",
  "tenantId": 331372985380245504,
  "userId": 63,
  "conversationId": 331500000000000001,
  "knowledgeBaseId": 331377006161694720,
  "history": [
    {
      "role": "USER",
      "content": "这篇论文使用了什么模型？"
    },
    {
      "role": "ASSISTANT",
      "content": "论文主要使用 Transformer 模型。"
    }
  ]
}
```

## 4. Java 会话接口

```text
POST   /api/chat/completions
GET    /api/chat/conversations
GET    /api/chat/conversations/{conversationId}
GET    /api/chat/conversations/{conversationId}/messages
DELETE /api/chat/conversations/{conversationId}
```

所有会话操作必须校验当前租户。用户不能通过猜测 ID 访问其他租户会话。

## 5. Python 历史使用方式

Python 将历史转换为 LangChain 消息：

```text
USER      -> human
ASSISTANT -> ai
```

消息顺序为：

```text
系统规则
-> 历史消息
-> 当前知识库上下文（存在时）
-> 当前问题
```

当前方案可以使用 LangChain 的消息类型或 `MessagesPlaceholder` 改善 Prompt 结构，但不将内存型 `RunnableWithMessageHistory` 作为唯一历史存储。

## 6. 历史窗口

Java 只加载最近若干条消息传给 Python，防止上下文无限增长。后续可以增加：

- Token 数量窗口。
- 历史消息摘要。
- 重要事实记忆。
- LangGraph checkpointer。

## 7. 验收标准

- 新问题可以创建会话。
- 带 `conversationId` 的问题可以继续原会话。
- 用户和助手消息均写入数据库。
- 刷新页面后仍能加载历史。
- 删除会话后消息不可继续访问。
- Python 能根据历史理解基础追问。

