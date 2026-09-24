# 本地环境与启动

[返回目录](README.md)

## 依赖与前提

准备 JDK 17、Maven、Python 虚拟环境、支持当前 Vite 的 Node.js/npm、PostgreSQL、S3 兼容存储和模型服务。Python 本地可与 Dockerfile 的 3.12 对齐。Redis 是否启用取决于实际绑定的 rag.redis.enabled。

当前聊天 Schema 迁移未完成，见 [限制清单](12-current-gaps.md)。服务能启动不表示端到端问答已通过。

## 配置加载

- Compose 从根 `.env` 读取变量替换，不会把变量自动注入本机 Maven 进程。
- Python `load_dotenv()` 加载环境，`get_settings()` 缓存；修改后重启。
- Java 从 Spring 配置与进程环境读取，不内置通用 `.env` 加载器；IDE 中也需配置环境变量。
- Vite 读取 `VITE_API_BASE_URL`，默认空字符串，开发走 `/api` 代理；生产修改需重新构建。

Java 的 RAG_DB_* 与 Python 的 POSTGRES_* 必须指向同一数据库。完整条目见 [配置参考](14-configuration-reference.md)。

## 数据库、存储、密钥

根目录执行，已有 `.env` 时不要覆盖：

```powershell
Copy-Item .env.example .env
# 编辑实际配置后启动
docker compose up -d postgres
docker compose ps
```

Compose 默认库 enterprise_rag、用户 rag、端口 5432，密码应显式配置。另备 S3 endpoint、bucket 和访问密钥；Compose 不提供 S3/Redis。

JWT 使用匹配的 RSA 密钥。已安装 OpenSSL 时可生成到新文件，避免覆盖已有密钥：

```powershell
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out secrets/jwt-private.pem
openssl pkey -in secrets/jwt-private.pem -pubout -out secrets/jwt-public.pem
```

JWT_*_KEY_PATH 填绝对文件路径，不再加 file:，Java YAML 已添加该前缀。

## Java

根目录独立终端：

```powershell
$env:RAG_DB_URL = 'jdbc:postgresql://127.0.0.1:5432/enterprise_rag'
$env:RAG_DB_USERNAME = 'rag'
$env:RAG_DB_PASSWORD = '<数据库密码>'
$env:RAG_STORAGE_ENDPOINT = 'http://127.0.0.1:9000'
$env:RAG_STORAGE_ACCESS_KEY_ID = '<访问键>'
$env:RAG_STORAGE_SECRET_ACCESS_KEY = '<存储密钥>'
$env:RAG_STORAGE_BUCKET = 'rag-documents'
$env:JWT_PRIVATE_KEY_PATH = 'E:/Data/AI/RAGagent/secrets/jwt-private.pem'
$env:JWT_PUBLIC_KEY_PATH = 'E:/Data/AI/RAGagent/secrets/jwt-public.pem'
$env:RAG_EMBEDDING_PYTHON_BASE_URL = 'http://127.0.0.1:9100'
mvn -pl java-api spring-boot:run
```

启动自动执行 Flyway。接入已有库先核对历史，不要通过启用 baseline 掩盖未知结构。V19 会锁聊天表、增加序列，应先审查。

探活使用 `/actuator/health`。Security 虽放行 `/api/health`，当前 Java 源码未找到对应 Controller。允许 Swagger 路径也不等于 Java 已提供 Swagger 页面。

## Python

在 python-api 目录独立终端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 9100 --reload
```

设置 POSTGRES_HOST/PORT/DB/USER/PASSWORD，EMBEDDING_BASE_URL/API_KEY/MODEL/DIMENSION，LLM_BASE_URL/API_KEY/MODEL；需要重排时设置 RERANK_*。默认 provider 虽写 mock，客户端仍创建 OpenAIEmbeddings，不能视为离线模式。

FastAPI lifespan 初始化数据库池；`/health` 返回 UP 不验证模型调用效果。`/docs` 和 `/openapi.json` 展示当前 Python 契约。uvicorn 命令的显式端口不依赖 APP_PORT。

## 前端

在 frontend 目录独立终端：

```powershell
npm.cmd ci
npm.cmd run dev
```

访问 `http://127.0.0.1:5173`。默认由 Vite proxy 转发到 8123；直连时设置 VITE_API_BASE_URL，并配置 Java CORS。修改依赖才用 npm install 并审查锁文件。

## 初始化与冒烟顺序

1. 检查 Flyway 成功历史及 V11/V13/V14 种子数据，核对账号角色，不传播种子口令。
2. 用已授权管理员登录，查询 `/api/auth/me`。
3. 创建测试知识库，明确模型与 1536 维约束，上传小型 UTF-8 文本。
4. 等待任务 SUCCESS、文档 READY，查看 Chunk 和检索调试结果。
5. 聊天迁移阻塞修复后，再验收同步问答、SSE、引用、历史及失败 Trace。

上传返回不表示入库结束；SSE done 不表示回答成功。
