# Java 后端开发

[返回目录](README.md)

## 分层与通用设施

通常按 controller → service/impl → mapper/entity 组织。Controller 接收 DTO、执行声明式权限并返回 ApiResult；Service 承担业务、租户检查和事务；MyBatis-Plus 处理实体，复杂查询和向量写入使用 SQL/JDBC。

ApiResult 成功体包含 success=true、code=OK、message=success、data 和 timestamp；分页从 1 开始。SSE 返回 SseEmitter，不包装 JSON。异常体系区分客户端、业务、服务端、数据库、远程调用与入库，由 GlobalExceptionHandler 映射；新增异常保留原因链。

Snowflake ID 可能超过 JavaScript 安全整数范围。数据库配置包括字段填充、分页和 JSONB TypeHandler。原生 SQL 需自行添加租户、逻辑删除条件；MyBatis 的实体逻辑删除不等于数据库全局隔离策略。

## 认证与上下文

Spring Security 使用无 Session JWT Resource Server，校验 RSA 签名及配置的声明验证，role Claim 映射为 ROLE_ 权限。Access Token 默认 15 分钟，Refresh Token 7 天。TokenVersionValidator 与用户 tokenVersion 配合撤销旧令牌。

登录和刷新公开；改密码、退出、全部退出需认证。RefreshTokenService 负责刷新令牌轮换/撤销；AccountSecurityService 处理密码和全设备退出。业务层不要直接接受前端传来的 userId 作为当前身份。

RequestContextFilter 在 Bearer 校验后恢复 LoginUser、requestId/MDC，并禁止 Servlet 重复注册。异步线程必须显式携带上下文，在 finally 清理，不能依赖 HTTP ThreadLocal 自动传播。

## 权限边界

| 角色 | 典型访问 |
| --- | --- |
| PLATFORM_ADMIN | 租户管理、实现允许的跨租户操作 |
| ADMIN | 本租户用户、知识库、文档、模型、任务、测评与 Trace |
| USER | 聊天、可用知识库与模型查询 |

TenantAccessGuard 对普通用户和租户管理员要求目标 tenantId 等于当前 tenantId；平台管理员可跨租户。会话还需核对 userId 所有权。实际 Controller 注解见 [API 参考](13-api-reference.md)，前端守卫不替代后端授权。

Actuator 的 health/info/metrics 当前公开。Security 放行 Swagger 路径，但 POM 未声明常见的 Springdoc 集成，不能据此承诺 Java API 文档页面。

## 租户、用户与知识库

TenantController 提供创建、详情、启用列表、禁用；UserController 提供列表、创建、详情、按租户/用户名查询、禁用。密码使用 BCrypt；用户输出采用 UserResponse，新增接口不要泄露 passwordHash。

知识库包含状态、domainCode、文档计数和 chunkStrategy。ensureUsable 检查知识库可用性，listAvailableForChat 服务于普通登录用户。文档保存对象 URI、SHA-256、文件大小、metadata 和状态。手动登记元数据不等于上传并索引；删除逻辑记录不等于物理清理 S3 对象。

## 模型管理

ModelProvider/ModelConfig 提供管理 CRUD，ModelQuery 提供登录用户的模型下拉列表。数据库记录不是 Python 的实时配置中心：Python endpoint/key/model 主要来自进程环境。聊天服务要求请求 model 与 LLM_MODEL 一致，因此下拉框展示不代表服务可执行。

Embedding 支持按模型名创建客户端，但通常共享环境中的地址和密钥。支持多个供应商需要明确路由与密钥选择，不能只新增一条模型记录。

## 跨服务调用

Embedding、Chat、Summary、RetrievalDebug、Evaluation 有独立 Python 客户端。契约变更同时核对 Java DTO、Python Schema、业务转换、前端类型与流事件。区分 HTTP 失败、success=false、反序列化失败、SSE 流内 error。

入库、聊天流、摘要使用不同执行器。调整并发需同步评估 Hikari、Python 连接池和模型额度。避免将完整远程调用包在大事务里；任务、Chunk、向量批次有专门持久化服务。

## 扩展入口

新增业务优先复制模块结构而非复制整个框架：定义请求/响应 → 角色和对象权限 → Service 事务 → Mapper/迁移 → Controller → 前端映射 → 正反向验证。不要因页面隐藏就省略后端权限，也不要让 Python 客户端接受任意客户端身份。

源码：[模块根目录](../../java-api/src/main/java/com/example/rag)、[SecurityConfig](../../java-api/src/main/java/com/example/rag/auth/config/SecurityConfig.java)、[TenantAccessGuard](../../java-api/src/main/java/com/example/rag/common/security/TenantAccessGuard.java)。
