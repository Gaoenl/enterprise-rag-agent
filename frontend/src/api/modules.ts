import { http, parseJsonSafely } from './http';
import { useAuthStore } from '../stores/authStore';
import axios from 'axios';
import type {
  ApiResult,
  ChatConversation,
  ChatKnowledgeBaseOption,
  ChatMessage,
  ChatRequest,
  CurrentUser,
  DocumentChunk,
  IngestionTaskDetail,
  IngestionTaskListItem,
  IngestionTaskQuery,
  IngestionTaskStatistics,
  IngestionTaskStatisticsQuery,
  IngestionTaskStep,
  KnowledgeBase,
  KnowledgeDocument,
  ModelConfig,
  ModelProvider,
  ModelType,
  PageResult,
  PipelineConfig,
  TokenResponse,
} from '../types/api';
export const authApi = {
  login: (v: { username: string; password: string }) =>
    http.post<never, TokenResponse>('/api/auth/login', v),
  me: () => http.get<never, CurrentUser>('/api/auth/me'),
  logout: (refreshToken: string) => http.post('/api/auth/logout', { refreshToken }),
};
export const kbApi = {
  page: (p: { keyword?: string; pageNo: number; pageSize: number }) =>
    http.get<never, PageResult<KnowledgeBase>>('/api/knowledge-bases', { params: p }),
  get: (id: string) => http.get<never, KnowledgeBase>(`/api/knowledge-bases/${id}`),
  create: (v: Pick<KnowledgeBase, 'name' | 'description' | 'visibility'> & {
    pipelineConfig?: PipelineConfig;
  }) =>
    http.post<never, KnowledgeBase>('/api/knowledge-bases', v),
  update: (id: string, v: Partial<KnowledgeBase> & {
    pipelineConfig?: PipelineConfig;
  }) =>
    http.patch<never, KnowledgeBase>(`/api/knowledge-bases/${id}`, v),
  remove: (id: string) => http.delete(`/api/knowledge-bases/${id}`),
};
export const documentApi = {
  list: (kbId: string) =>
    http.get<never, KnowledgeDocument[]>(`/api/documents/by-knowledge-base/${kbId}`),
  get: (id: string) => http.get<never, KnowledgeDocument>(`/api/documents/${id}`),
  chunks: (id: string) => http.get<never, DocumentChunk[]>(`/api/documents/${id}/chunks`),
  remove: (id: string) => http.delete(`/api/documents/${id}`),
  batchRemove: (ids: string[]) => http.post('/api/documents/batch-delete', ids),
  // 根据文档 ID 触发后端完整入库流程：解析、切分、Chunk 入库和向量化。
  process: (id: string) =>
    http.post<never, void>(`/api/ingestion/tasks/documents/${id}/process`, undefined, {
      // 文档解析和模型调用属于长耗时操作，单独放宽为 10 分钟。
      timeout: 10 * 60 * 1000,
    }),
  upload: (kbId: string, files: File[], onProgress: (n: number) => void) => {
    const data = new FormData();
    data.append('knowledgeBaseId', kbId);
    // 多个文件使用同一个 file 字段名，后端接收为 List<MultipartFile>。
    files.forEach((file) => data.append('file', file));
    return http.post<never, KnowledgeDocument[]>('/api/documents/upload', data, {
      onUploadProgress: (e) => onProgress(e.total ? Math.round((e.loaded / e.total) * 100) : 0),
      timeout: 10 * 60 * 1000,
    });
  },
};
export const taskApi = {
  page: (params: IngestionTaskQuery) =>
    http.get<never, PageResult<IngestionTaskListItem>>('/api/ingestion/tasks', { params }),
  statistics: (params: IngestionTaskStatisticsQuery = {}) =>
    http.get<never, IngestionTaskStatistics>('/api/ingestion/tasks/statistics', { params }),
  get: (id: string) => http.get<never, IngestionTaskDetail>(`/api/ingestion/tasks/${id}`),
  steps: (id: string) => http.get<never, IngestionTaskStep[]>(`/api/ingestion/tasks/${id}/steps`),
  getByDocument: (docId: string) =>
    http.get<never, IngestionTaskDetail>(`/api/ingestion/tasks/by-document/${docId}`),
  retry: (id: string) => http.post(`/api/ingestion/tasks/${id}/retry`),
};
export const chatApi = {
  /** 所有登录用户都可查询，用于 RAG 对话的知识库选择。 */
  availableKnowledgeBases: () =>
    http.get<never, ChatKnowledgeBaseOption[]>('/api/chat/knowledge-bases'),
  conversations: (p: { keyword?: string; pageNo: number; pageSize: number }) =>
    http.get<never, PageResult<ChatConversation>>('/api/chat/conversations', { params: p }),
  messages: (id: string) =>
    http.get<never, ChatMessage[]>(`/api/chat/conversations/${id}/messages`),
  remove: (id: string) => http.delete(`/api/chat/conversations/${id}`),
};
export const userApi = {
  list: () => http.get<never, import('../types/api').UserInfo[]>('/api/users'),
  create: (v: { username: string; password: string; displayName?: string; roleCode: string }) =>
    http.post<never, import('../types/api').UserInfo>('/api/users', v),
  disable: (id: string) => http.patch(`/api/users/${id}/disable`),
};

export const traceApi = {
  list: (params: { status?: string; keyword?: string; conversationId?: string; pageNo: number; pageSize: number }) =>
    http.get<never, PageResult<import('../types/api').RagTraceListItem>>('/api/rag/traces', { params }),
  get: (id: string) => http.get<never, import('../types/api').RagTraceDetail>(`/api/rag/traces/${id}`),
  statistics: () => http.get<never, import('../types/api').RagTraceStatistics>('/api/rag/traces/statistics'),
};
export const modelApi = {
  // Provider
  createProvider: (v: Partial<ModelProvider>) =>
    http.post<never, ModelProvider>('/api/model-providers', v),
  updateProvider: (id: string, v: Partial<ModelProvider>) =>
    http.patch<never, ModelProvider>(`/api/model-providers/${id}`, v),
  deleteProvider: (id: string) =>
    http.delete(`/api/model-providers/${id}`),
  listProviders: (params: { keyword?: string; pageNo: number; pageSize: number }) =>
    http.get<never, PageResult<ModelProvider>>('/api/model-providers', { params }),
  listProvidersAvailable: () =>
    http.get<never, ModelProvider[]>('/api/model-providers/available'),
  // Config
  createConfig: (v: Partial<ModelConfig>) =>
    http.post<never, ModelConfig>('/api/model-configs', v),
  updateConfig: (id: string, v: Partial<ModelConfig>) =>
    http.patch<never, ModelConfig>(`/api/model-configs/${id}`, v),
  deleteConfig: (id: string) =>
    http.delete(`/api/model-configs/${id}`),
  listConfigs: (params: { providerId?: string; modelType?: string; keyword?: string; pageNo: number; pageSize: number }) =>
    http.get<never, PageResult<ModelConfig>>('/api/model-configs', { params }),
  // 公开接口
  listByType: (type: ModelType) =>
    http.get<never, ModelConfig[]>(`/api/models?type=${type}`),
};

export const streamChat = async (
  request: ChatRequest,
  onEvent: (event: string, data: unknown) => void,
  signal: AbortSignal,
) => {
  const doFetch = async (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${http.defaults.baseURL}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(request),
      signal,
    });
  };

  let token = useAuthStore.getState().accessToken;
  let response = await doFetch(token);

  // 401 → 尝试刷新 token 后重试一次
  if (response.status === 401 && useAuthStore.getState().refreshToken) {
    try {
      const refreshResponse = await axios.post<ApiResult<TokenResponse>>(
        `${http.defaults.baseURL}/api/auth/refresh`,
        { refreshToken: useAuthStore.getState().refreshToken },
        { transformResponse: [(data: string) => parseJsonSafely(data)] },
      );
      const newSession = refreshResponse.data.data;
      useAuthStore.getState().setSession(newSession);
      token = newSession.accessToken;
      response = await doFetch(token);
    } catch {
      useAuthStore.getState().clear();
      window.location.assign('/login');
      throw new Error('登录已过期，请重新登录');
    }
  }

  if (!response.ok || !response.body) {
    if (response.status === 401) {
      useAuthStore.getState().clear();
      window.location.assign('/login');
      throw new Error('登录已过期');
    }
    throw new Error(`流式请求失败：${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  // 空闲超时：长时间没有收到任何数据时中止，避免"永久缓冲"。
  // 模型长回答可能间隔较久，这里给足 120 秒。
  const IDLE_TIMEOUT_MS = 120_000;
  while (true) {
    let result: ReadableStreamReadResult<Uint8Array>;
    try {
      result = await Promise.race([
        reader.read(),
        new Promise<never>((_, reject) => {
          setTimeout(
            () => reject(new Error('生成超时，连接已中断，请重试')),
            IDLE_TIMEOUT_MS,
          );
        }),
      ]);
    } catch (error) {
      // 超时后主动关闭响应流，释放连接，再把错误抛给调用方展示。
      try {
        await reader.cancel();
      } catch {
        // 关闭失败不影响错误上抛。
      }
      throw error;
    }
    const { done, value } = result;
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      let event = 'message',
        data = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (data) {
        let parsed: unknown = data;
        try {
          parsed = parseJsonSafely(data);
        } catch {
          // 非 JSON data 仍按原始文本交给调用方处理。
        }
        onEvent(event, parsed);
      }
    }
  }
};
