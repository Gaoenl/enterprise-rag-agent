# 部署与运维

[返回目录](README.md)

## 仓库实际提供的部署资产

Compose 只部署 PostgreSQL；Python 有 Dockerfile；前端有 build 产物流程。未提供全栈 Compose、Java Dockerfile、生产反向代理或完整 CI/CD。以下是部署操作要求，不声称这些设施已经落地。

Java 可用 Maven spring-boot:run 本地启动。若交付可执行 JAR，应检查 Spring Boot repackage：父 POM 不是 Boot parent，不能只凭 package 命令假定已生成可执行包。可在验证环境执行：

```powershell
mvn -pl java-api package spring-boot:repackage -DskipTests
java -jar java-api/target/java-api-0.1.0-SNAPSHOT.jar
```

上例 skipTests 只是打包选项，不替代交付前测试。Python 镜像构建上下文是 python-api；模型凭据使用运行时环境注入，不打进镜像。前端发布 dist。

## 推荐拓扑和启动顺序

浏览器 → TLS 反向代理 → 静态前端及 Java /api → 内网 Python；数据库、Redis、S3 和模型端点按最小必要网络开放。Python 信任内部传入身份，不应直接暴露给任意客户端。

顺序：备份/核对迁移 → 数据库与存储 → Java 执行已审查迁移 → Python → Java/Python 联通检查 → 前端 → 冒烟。当前会话迁移不完整，禁止把聊天端到端验收省略。

server profile 必须提供 RAG_DB_URL/USERNAME/PASSWORD，且 application-server.yml 将 baseline-on-migrate 设为 true，覆盖基础配置的谨慎默认值。启用前应明确是否允许对非空库建基线。

## 代理要求

前端使用浏览器路由，未知前端路径回退 index.html；/api 要转发到 Java，不可落到静态回退。SSE 关闭代理缓冲和缓存，设置足够的读超时，保留 Authorization、Content-Type、X-Request-Id。上传限制与 Java 100MB/120MB 对齐。

Java CORS 允许的是 Origin，不带路径。前端 VITE_API_BASE_URL 是构建时配置；生产同源部署可留空。不要把前端改环境变量却未重新构建视为已切换 API。

## 容量与扩容边界

Hikari 默认最大 10、最小 2；Python psycopg 池按 POSTGRES_POOL_* 配置，进程数乘以每进程池大小才是总连接需求。入库池最大 4、队列 50；评测池每进程 1；意图分类另有线程池。模型限流与数据库连接需一起预算。

上传完整文件读入内存，多并发大文件会增加堆压力。SSE 长连接占用执行资源。评测状态在单进程字典，不能直接启用多 worker 保证一致查询。入库事件非持久队列，发布/重启过程需要检查未完成任务。

## 备份与恢复

数据库备份覆盖业务表、向量、序列、Flyway 历史；S3 备份覆盖原始对象；另保护 JWT 密钥和配置。Redis 是可恢复缓存，不替代数据库历史。

恢复时核对文档 URI 与对象存在性、向量模型与维度、会话 ID 序列和迁移版本。涉及 V19 时协调聊天写入方并检查最大 ID。数据库回退与新版本写入兼容性要先评估，不能只回滚 JAR。

## 排障表

| 现象 | 优先核对 |
| --- | --- |
| Java 启动缺配置 | 存储凭据、JWT 文件路径、进程环境而非仅 .env |
| Flyway 失败 | 数据库历史、脚本 checksum、扩展权限、V19 锁 |
| `/api/health` 404 | Java 当前用 `/actuator/health` |
| Python 启动失败 | 数据库连接池、依赖、配置、循环导入/契约变更 |
| Embedding 401/502 | 真实 endpoint/key/model，mock 默认并非实现 |
| 向量维度错误 | Python/Java 配置、模型输出、vector(1536) |
| 上传成功但无结果 | 任务/步骤状态、原对象、解析文本、批次错误 |
| RUNNING 长期不变 | 进程中断、事件线程、外部超时；无自动补偿保证 |
| Redis 未使用 | rag.redis.enabled 与 YAML 缩进/前缀 |
| Chat history AttributeError | 当前 ChatRequest 与 ChatService 迁移不兼容 |
| SSE 卡住或整段返回 | 代理缓冲、事件空行、模型耗时、final/done |
| 检索空结果 | 租户/知识库/删除状态、入库、模型维度、关键词 |
| 测评 runId 丢失 | Python 重启或请求落到另一 worker |
| 前端 ID 对不上 | Long 是否被转成 Number，是否绕过 JSONBig |

先关联 requestId/taskId/traceId 查日志，再看步骤/Trace；不要把所有 502 都归结为 LLM，也不要把 Python health=UP 当作完整下游健康检查。
