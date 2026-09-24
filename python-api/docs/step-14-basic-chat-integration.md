# Step 14：基础问答与 Java/Python Chat 集成

## 1. 目标

本步骤建立最小可用的提问到回答链路：

```text
Frontend
  -> Java Chat API
  -> Python Chat API
  -> LangChain ChatModel
  -> Java
  -> Frontend
```

当前阶段先验证真实模型能够根据用户问题生成回答，不加入检索、路由、工具和 Agent。

## 2. Java 与 Python 的职责

Java 是面向前端的业务入口，负责：

- 接收聊天请求。
- 从用户上下文取得租户和用户信息。
- 调用 Python Chat API。
- 将 Python 响应转换为统一的 `ApiResult`。
- 记录远程调用异常和业务日志。

Python 是智能编排入口，负责：

- 校验聊天参数。
- 根据配置选择真实 LLM。
- 使用 LangChain 调用模型。
- 返回统一的 Chat 响应结构。

前端在正式架构中只调用 Java，不直接依赖 Python 服务。

## 3. Python 主要文件

```text
python-api/app/
├─ api/chat_api.py
├─ clients/llm_client.py
├─ factories/chat_model_factory.py
├─ schemas/chat_schema.py
└─ services/chat_service.py
```

`chat_api.py` 类似 Java Controller；`chat_service.py` 负责编排；`llm_client.py` 负责模型调用；`chat_model_factory.py` 统一创建并缓存 LangChain ChatModel。

## 4. Java 主要文件

```text
java-api/src/main/java/com/example/rag/chat/
├─ controller/ChatController.java
├─ service/ChatService.java
├─ service/impl/ChatServiceImpl.java
├─ client/PythonChatClient.java
├─ client/dto/
└─ dto/
```

Java 调用 Python：

```http
POST /api/chat/completions
Content-Type: application/json
```

基础请求：

```json
{
  "question": "介绍一下 RAG 的基本过程",
  "model": "qwen-plus",
  "history": []
}
```

## 5. LangChain 模型调用

`LlmClient` 将消息组织为：

```text
SystemMessage
History Messages
Current HumanMessage
```

基础系统提示词约束模型作为企业级 RAG 智能助手回答。模型配置从环境变量读取，API Key 不写入源码。

## 6. 异常处理

- Python 模型调用失败时返回明确的 HTTP 错误。
- Java 收到非 2xx 响应时抛出 `RemoteException`。
- Java 日志记录状态码和响应体，但不打印 API Key。
- 前端只接收统一业务错误结构。

## 7. 验收标准

- Python `/docs` 可以看到 Chat API。
- Python Chat API 能返回真实模型回答。
- Java 能成功调用 Python Chat API。
- 前端通过 Java 能完成一次基础问答。
- Python 不负责租户、用户和正式业务数据写入。

