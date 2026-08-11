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
  /** 是否启用多查询召回。 */
  enableMultiQuery?: boolean;
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
  /** 多查询召回实际使用的子查询列表。 */
  alternativeQueries: string[];
  /** 多路向量候选合并去重后的数量。 */
  vectorMergedCount: number;
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

/** 检索调试默认参数（来自服务端配置）。 */
export interface RetrievalConfig {
  vectorTopK: number;
  keywordTopK: number;
  fusionTopK: number;
  finalTopK: number;
  rrfK: number;
  vectorWeight: number;
  keywordWeight: number;
  multiQueryEnabled: boolean;
  multiQueryTopK: number;
  synonymExpansionEnabled: boolean;
}
