# 前端开发

[返回目录](README.md)

## 工程组织

入口 main.tsx 组织应用，AppRouter 定义浏览器路由；ConsoleLayout 为聊天布局，AdminLayout 为管理布局。Ant Design 提供表单、表格等，React Query 管理服务端查询，Zustand 管理认证，ECharts 用于统计，MarkdownRenderer 展示回答。

| 目录 | 责任 |
| --- | --- |
| api | Axios、认证刷新、业务请求、fetch SSE |
| pages | 业务页面、表单和交互 |
| components | Markdown、错误边界、图表、检索结果和上下文 |
| router / layouts | 登录与管理员守卫、页面导航 |
| stores | Token 和当前用户 |
| types | Java/Python 返回值映射 |
| styles / utils | 主题和角色判断 |

## 已注册页面

| 路径 | 页面 | 数据来源 |
| --- | --- | --- |
| /login | LoginPage | auth/login、me |
| /、/chat | ChatPage | 会话、消息、SSE、可用知识库/模型 |
| /admin | DashboardPage | 后台统计 |
| /admin/knowledge | KnowledgePage | 知识库 CRUD |
| /admin/knowledge/:knowledgeBaseId/documents | DocumentsPage | 上传、文档、Chunk |
| /admin/tasks | TaskPage | 入库任务、步骤、统计、重试 |
| /admin/retrieval | RagEvaluationPage | 检索测评 |
| /admin/traces | TracePage | Trace 列表、详情、统计 |
| /admin/models | ModelPage | 供应商/模型配置 |
| /admin/settings | SettingsPage | 管理设置相关界面 |

HomePage、PlaceholderPage、RetrievalDebugPage 文件存在，但当前 AppRouter 未注册相应独立路由；不要仅根据文件名宣称可访问。后端具备某个 CRUD 也不代表前端已有完整页面。

## 登录与 HTTP

Guard 检查 accessToken；AdminRouteGuard 校验管理员。authStore 把 Token 存入 localStorage 或 sessionStorage，默认 remember=true；设置时清除另一种存储，退出清除两者。

http.ts 的 baseURL 默认空，开发 Vite 把 /api 转到 8123，普通请求超时 30 秒。请求拦截器加 Bearer；响应自动解包 ApiResult.data，success=false 转 ApiError。401 对非 auth 请求最多重试一次；并发刷新复用一个 Promise，失败清理会话并跳登录。

JSONBig 使用 storeAsString，避免后端 Long 精度丢失。SSE 也使用 parseJsonSafely。新增 ID 字段应保留现有类型规则，不用 Number(id) 或 parseInt 后再发请求。

## 流式页面

api/modules.ts 的 streamChat 使用 fetch 和 AbortSignal，处理 401 后单次刷新重试，增量解码并按空行解析 event/data。页面处理 route/retrieval 状态、delta 草稿、final 引用、error/done。

新增事件必须同时更新 Python 编码、Java 转发、TypeScript 类型和页面处理。普通 Axios 的 30 秒超时不直接适用于 fetch 长连接；组件卸载与用户取消要使用 AbortController。

## 开发步骤

1. 先核对实际后端路由和返回形状，在 types 定义准确类型。
2. 在 api 中封装请求，不在多个页面复制认证逻辑。
3. 页面处理 loading、空数据、失败、分页、权限和取消。
4. 操作成功后更新相关查询缓存，避免上传/删除后展示旧计数。
5. 新路由同时更新菜单与守卫，验证刷新/直达/未登录状态。

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

包中没有 test 脚本。生产部署 dist，需 SPA 路由回退；vite preview 是预览工具，不应被文档当作已提供的生产部署方案。

源码：[路由](../../frontend/src/router/AppRouter.tsx)、[HTTP](../../frontend/src/api/http.ts)、[业务与 SSE](../../frontend/src/api/modules.ts)、[认证 Store](../../frontend/src/stores/authStore.ts)。
