# Step 24: Java SSE Chat Proxy

## 1. Goal

Expose a Java streaming chat endpoint while keeping Python responsible for RAG
orchestration and token streaming. The frontend continues to call Java instead
of accessing Python directly.

## 2. Request Flow

```text
Frontend
  -> Java POST /api/chat/stream
  -> Java validates tenant and user
  -> Java creates or validates the conversation
  -> Java saves the user message in a short transaction
  -> Java calls Python POST /api/chat/stream
  -> Python returns SSE events
  -> Java forwards start/route/retrieval/delta events
  -> Java parses final and saves assistant message plus RAG trace
  -> Java forwards final/done to the frontend
```

## 3. Java Responsibilities

- Read tenant and user IDs from `UserContext`.
- Never trust tenant or user IDs supplied by the frontend.
- Create or validate the conversation.
- Load recent persisted messages and build `PythonChatRequest`.
- Generate `traceId` and `requestId`.
- Persist the user message before starting the remote stream.
- Proxy Python SSE events without rewriting generated text.
- Parse the `final` event for persistence.
- Persist the assistant message and successful trace in a short transaction.
- Persist a failed trace when the Python request fails before `final`.

## 4. Transaction Boundary

Do not place one transaction around the complete SSE method.

```text
Transaction A:
  create conversation
  save user message
  commit

No transaction:
  call Python
  forward SSE stream

Transaction B:
  save assistant message
  save successful trace
  update conversation
  commit
```

Keeping a database transaction open during LLM generation would hold database
connections and locks for the complete streaming lifetime.

## 5. Planned Java Files

```text
chat/
├── client/
│   ├── PythonChatClient.java
│   └── sse/
│       ├── PythonSseEvent.java
│       └── PythonSseEventParser.java
├── controller/
│   └── ChatController.java
├── service/
│   ├── ChatService.java
│   └── impl/
│       └── ChatServiceImpl.java
└── transaction/
    └── ChatPersistenceService.java
```

## 6. SSE Contract

Supported events:

- `start`: request and conversation identifiers.
- `route`: intent and RAG decision.
- `retrieval`: retrieval stage counts.
- `delta`: incremental model text.
- `final`: authoritative post-processed answer, citations and trace.
- `error`: stream failure details.
- `done`: normal or error stream termination.
- `heartbeat`: optional connection heartbeat.

Only `final.data.answer` is persisted as the assistant message. Concatenated
`delta` text is display-only because answer post-processing may change the final
text.

## 7. Cancellation

When the browser disconnects, Java should cancel the downstream Python HTTP
request. If no `final` event was received, Java must not persist an assistant
message and should record the trace as failed or cancelled.

