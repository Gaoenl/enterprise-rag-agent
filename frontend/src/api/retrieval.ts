import { http } from './http';
import type {
  RetrievalConfig,
  RetrievalDebugRequest,
  RetrievalDebugResponse,
} from '../types/retrieval';

/** 检索调试接口。 */
export const retrievalApi = {
  debug: (request: RetrievalDebugRequest) =>
    http.post<never, RetrievalDebugResponse>('/api/retrieval/debug', request, {
      // Rewrite、Embedding 和 Rerank 都可能调用远程模型。
      timeout: 120_000,
    }),
  /** 获取检索调试默认参数（按服务端配置初始化表单）。 */
  getConfig: () => http.get<never, RetrievalConfig>('/api/retrieval/config'),
};
