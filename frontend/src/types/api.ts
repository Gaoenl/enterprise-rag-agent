export interface ApiResult<T> {
  success: boolean;
  code: string;
  message: string;
  data: T;
  timestamp: string;
}
export interface PageResult<T> {
  records: T[];
  total: number;
  pageNo: number;
  pageSize: number;
  pages: number;
  hasNext: boolean;
}
export interface TokenResponse {
  tokenType: string;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  userId: string;
  tenantId: string;
  username: string;
  displayName: string;
  role: string;
}
export interface UserInfo {
  id: string;
  tenantId: string;
  username: string;
  displayName?: string;
  email?: string;
  roleCode: string;
  status: number;
  lastLoginAt?: string;
  createdAt: string;
}

export interface CurrentUser {
  userId: string;
  tenantId: string;
  username: string;
  displayName: string;
  email?: string;
  roleCode: string;
}

/** RAG 对话中可选择的轻量知识库信息。 */
export interface ChatKnowledgeBaseOption {
  id: string;
  name: string;
}

// --- 枚举类型 ---

export type KnowledgeBaseVisibility = 'PRIVATE' | 'TENANT' | 'PUBLIC';
export type DocumentParseStatus =
  | 'PENDING'     // 排队中
  | 'PROCESSING'  // 解析切分中
  | 'PARSED'      // 已解析，等待向量化
  | 'EMBEDDING'   // 向量化中
  | 'READY'       // 处理完成
  | 'FAILED';     // 处理失败
export type IngestionTaskType = 'DOCUMENT_INGEST' | 'EMBEDDING';
export type IngestionStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELED';
export type ChatChannel = 'WEB' | 'API';
export type MessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM';

// --- 实体类型 ---

/** 入库流水线配置——对应后端 PipelineConfig 实体。 */
export interface PipelineConfig {
  chunkType?: string;
  chunkSize?: number;
  chunkOverlap?: number;
  embeddingModel?: string;
  embeddingDimension?: number;
  embeddingBatchSize?: number;
}

export interface KnowledgeBase {
  id: string;
  tenantId: string;
  name: string;
  description?: string;
  visibility: KnowledgeBaseVisibility;
  /** 业务域编码，用于意图 L1 路由按域过滤知识库。 */
  domainCode?: DomainCode;
  embeddingModelConfigId?: string;
  /** 流水线配置 JSON 对象，可能为 null（旧数据）或空对象。 */
  chunkStrategy?: PipelineConfig | null;
  status: number;
  documentCount: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deleted: boolean;
}

/** 知识库业务域。 */
export type DomainCode = 'EXPENSE' | 'HR' | 'CONTRACT' | 'POLICY' | 'GENERAL';
export interface KnowledgeDocument {
  id: string;
  tenantId: string;
  knowledgeBaseId: string;
  fileName: string;
  fileType: string;
  fileUri: string;
  fileSize: number;
  contentHash: string;
  parseStatus: DocumentParseStatus;
  metadata: Record<string, unknown>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deleted: boolean;
}
export interface DocumentChunk {
  id: string;
  documentId: string;
  chunkIndex: number;
  content: string;
  tokenCount?: number;
  embeddingModel?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}
export interface IngestionTask {
  id: string;
  tenantId: string;
  knowledgeBaseId: string;
  documentId: string;
  taskType: IngestionTaskType;
  status: IngestionStatus;
  errorMessage?: string;
  progress: number;
  startedAt?: string;
  finishedAt?: string;
  createdAt: string;
  updatedAt: string;
}

/** 任务中心分页查询条件，与后端 IngestionTaskQueryRequest 对齐。 */
export interface IngestionTaskQuery {
  keyword?: string;
  status?: IngestionStatus;
  taskType?: IngestionTaskType;
  knowledgeBaseId?: string;
  documentId?: string;
  createdBy?: string;
  createdAtStart?: string;
  createdAtEnd?: string;
  pageNo: number;
  pageSize: number;
}

/** 任务中心列表项，与后端 IngestionTaskListResponse 对齐。 */
export interface IngestionTaskListItem extends IngestionTask {
  knowledgeBaseName?: string;
  documentName?: string;
  currentStepCode?: string;
  currentStepName?: string;
  durationMillis?: number;
  createdBy?: string;
}

/** 任务详情，与后端 IngestionTaskDetailResponse 对齐。 */
export interface IngestionTaskDetail extends IngestionTaskListItem {
  fileType?: string;
  fileSize?: number;
  documentStatus?: DocumentParseStatus;
  canRetry: boolean;
  steps: IngestionTaskStep[];
  knowledgeBaseDeleted?: boolean;
  documentDeleted?: boolean;
}

/** 任务统计，与后端 IngestionTaskStatisticsResponse 对齐。 */
export interface IngestionTaskStatistics {
  totalCount: number;
  pendingCount: number;
  runningCount: number;
  successCount: number;
  failedCount: number;
  successRate: number;
  averageDurationMillis: number;
  todayCreatedCount: number;
  todaySuccessCount: number;
  todayFailedCount: number;
}

/** 任务统计查询条件，与后端 IngestionTaskStatisticsQuery 对齐。 */
export interface IngestionTaskStatisticsQuery {
  knowledgeBaseId?: string;
  createdAtStart?: string;
  createdAtEnd?: string;
}

export interface IngestionTaskStep {
  id: string;
  taskId: string;
  stepCode: string;
  stepName: string;
  status: IngestionStatus;
  errorMessage?: string;
  startedAt?: string;
  finishedAt?: string;
  durationMillis?: number;
}
export interface ChatConversation {
  id: string;
  tenantId: string;
  userId: string;
  knowledgeBaseId?: string;
  title: string;
  channel: ChatChannel;
  createdAt: string;
  updatedAt: string;
}
export interface ChatMessage {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: string;
  citations?: unknown[];
  traceId?: string;
  createdAt: string;
}
export interface ChatRequest {
  conversationId?: string;
  knowledgeBaseId?: string;
  question: string;
  model?: string;
}

// --- Trace 类型 ---

export type TraceStatus = 'RUNNING' | 'SUCCESS' | 'DEGRADED' | 'FAILED';

export interface RagTraceListItem {
  id: string;
  conversationId: string;
  status: TraceStatus;
  latencyMs: number | null;
  question: string | null;
  intent: string | null;
  degraded: boolean;
  userId?: string;
  username?: string;
  createdAt: string;
}

export interface RagTraceDetail {
  id: string;
  tenantId: string;
  conversationId: string;
  messageId: string;
  traceType: string;
  requestId: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  nodes: TraceNode[];
  tokenUsage: { inputTokens: number; outputTokens: number; totalTokens: number };
  degradedReasons: string[];
  latencyMs: number | null;
  status: TraceStatus;
  errorMessage: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  parseError: boolean;
}

export interface TraceNode {
  name: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  latencyMs: number | null;
  inputSummary: Record<string, unknown>;
  outputSummary: Record<string, unknown>;
  errorMessage: string | null;
}

export interface RagTraceStatistics {
  totalCount: number;
  successCount: number;
  failedCount: number;
  degradedCount: number;
  successRate: number;
  avgLatencyMs: number;
  todayCount: number;
}

export interface RagTraceQuery {
  status?: TraceStatus;
  keyword?: string;
  conversationId?: string;
  pageNo: number;
  pageSize: number;
}

// --- 模型管理 ---

export type ModelType = 'EMBEDDING' | 'LLM' | 'RERANK';

export interface ModelProvider {
  id: string;
  tenantId?: string | null;
  providerCode: string;
  providerName: string;
  endpoint?: string;
  authType: string;
  status: number;
}

export interface ModelConfig {
  id: string;
  tenantId?: string | null;
  providerId: string;
  providerName?: string;
  modelCode: string;
  modelName: string;
  modelType: ModelType;
  parameters?: string;
  /** 支持的向量维度列表（后端返回该字段时优先使用，否则从 parameters 解析）。 */
  dimensions?: number[];
  isDefault: boolean;
  status: number;
}
