/** 检索调试模式。 */
export type RetrievalMode = 'VECTOR' | 'KEYWORD' | 'HYBRID';

/** 检索调试请求，与 Java RetrievalDebugRequest 对齐。 */
export interface RetrievalDebugRequest {
  /** 不传则检索当前租户全部知识库。 */
  knowledgeBaseId?: string;
  question: string;
  mode: RetrievalMode;
  enableRewrite: boolean;
  enableRerank: boolean;
  vectorTopK?: number;
  keywordTopK?: number;
  fusionTopK?: number;
  finalTopK?: number;
  rrfK?: number;
  vectorWeight?: number;
  keywordWeight?: number;
}

/** 检索阶段返回的候选分片。 */
export interface RetrievalCandidate {
  chunkId: string;
  documentId: string;
  knowledgeBaseId: string;
  chunkIndex: number;
  documentName: string | null;
  content: string;
  vectorScore: number | null;
  keywordScore: number | null;
  fusionScore: number | null;
  rerankScore: number | null;
  vectorRank: number | null;
  keywordRank: number | null;
  fusionRank: number | null;
  rerankRank: number | null;
  retrievalSources: string[];
  metadata: Record<string, unknown>;
  citationIndex: number | null;
  contextTruncated: boolean;
}

/** 最终上下文打包结果。 */
export interface PackedContext {
  text: string;
  totalChars: number;
  truncated: boolean;
  documents: RetrievalCandidate[];
}

/** Java Long 经过 JSONBig 解析后可能是字符串。 */
export type TimingValue = number | string;

/** 各检索阶段耗时，单位为毫秒。 */
export interface RetrievalTimings {
  rewriteMillis: TimingValue;
  vectorMillis: TimingValue;
  keywordMillis: TimingValue;
  fusionMillis: TimingValue;
  rerankMillis: TimingValue;
  packingMillis: TimingValue;
  totalMillis: TimingValue;
}

/** 检索调试完整响应。 */
export interface RetrievalDebugResponse {
  originalQuery: string;
  semanticQuery: string;
  keywords: string[];
  mode: RetrievalMode;
  rewriteApplied: boolean;
  rerankApplied: boolean;
  degraded: boolean;
  vectorResults: RetrievalCandidate[];
  keywordResults: RetrievalCandidate[];
  fusionResults: RetrievalCandidate[];
  rerankResults: RetrievalCandidate[];
  packedContext: PackedContext;
  timings: RetrievalTimings;
  warnings: string[];
}
