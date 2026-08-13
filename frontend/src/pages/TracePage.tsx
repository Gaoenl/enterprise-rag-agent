import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Button, Card, Col, Collapse, Descriptions, Drawer, Input, Row,
  Select, Space, Statistic, Table, Tag, Typography,
} from 'antd';
import {
  ClockCircleOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, StopOutlined,
} from '@ant-design/icons';
import { traceApi } from '../api/modules';
import { PageHeader } from '../components/PageHeader';
import type { TraceStatus, TraceNode, RagTraceListItem } from '../types/api';

const STATUS_META: Record<TraceStatus, { color: string; text: string; icon: React.ReactNode }> = {
  RUNNING:   { color: 'processing', text: '运行中', icon: <ClockCircleOutlined /> },
  SUCCESS:   { color: 'success',    text: '成功',   icon: <CheckCircleOutlined /> },
  DEGRADED:  { color: 'warning',    text: '降级',   icon: <WarningOutlined /> },
  FAILED:    { color: 'error',      text: '失败',   icon: <CloseCircleOutlined /> },
};

const NODE_COLORS: Record<string, string> = {
  SUCCESS: 'green', FAILED: 'red', SKIPPED: 'gray',
};

type NodeGroup = 'query' | 'retrieval' | 'generation' | 'tool';

/** 节点 → 分组 + 中文标签 + 关键字段白名单。 */
const NODE_META: Record<string, {
  group: NodeGroup;
  label: string;
  inputKeys?: string[];
  outputKeys?: string[];
}> = {
  QUERY_RESOLVE: {
    group: 'query', label: '问题独立化',
    inputKeys: ['historyCount'],
    outputKeys: ['rewritten', 'standaloneQuery'],
  },
  QUERY_ROUTE: {
    group: 'query', label: '意图路由',
    outputKeys: ['intent', 'domain', 'needRag', 'confidence', 'reason', 'routerPath', 'inheritContext'],
  },
  KNOWLEDGE_BASE_SELECT: {
    group: 'query', label: '知识库选择',
    outputKeys: ['knowledgeBaseId', 'selectionType', 'needClarification'],
  },
  RETRIEVAL_QUERY_REWRITE: {
    group: 'query', label: '检索查询改写',
    outputKeys: ['semanticQuery', 'keywords'],
  },
  HYBRID_RETRIEVE: {
    group: 'retrieval', label: '混合检索',
    outputKeys: ['candidateCount', 'vectorCount', 'keywordCount', 'multiQueryCount', 'fusedCount'],
  },
  RERANK: {
    group: 'retrieval', label: '重排',
    outputKeys: ['inputCount', 'resultCount'],
  },
  CONTEXT_PACK: {
    group: 'retrieval', label: '上下文打包',
    outputKeys: ['documentCount', 'totalChars', 'truncated'],
  },
  LLM_GENERATE: {
    group: 'generation', label: 'LLM 生成',
    inputKeys: ['model', 'streaming'],
    outputKeys: ['modelName', 'answerChars', 'inputTokens', 'outputTokens', 'totalTokens'],
  },
  ANSWER_POST_PROCESS: {
    group: 'generation', label: '回答后处理',
    outputKeys: ['answerStatus', 'usedCitationIndexes', 'invalidCitationIndexes'],
  },
  TOOL_EXECUTE: {
    group: 'tool', label: '工具执行',
    inputKeys: ['tool', 'input'],
    outputKeys: ['resultChars'],
  },
};

const GROUP_ORDER: NodeGroup[] = ['query', 'retrieval', 'generation', 'tool'];

const GROUP_TITLES: Record<NodeGroup, string> = {
  query: '查询理解',
  retrieval: '检索',
  generation: '生成',
  tool: '工具',
};

/** 节点输入/输出摘要：只展示关键字段，其余折叠在"其他"。 */
function NodeSummary({
  summary,
  keys,
}: {
  summary: Record<string, unknown>;
  keys?: string[];
}) {
  const entries = Object.entries(summary);
  if (entries.length === 0) return null;
  const primary = entries.filter(([key]) => !keys || keys.includes(key));
  const rest = entries.filter(([key]) => !keys || !keys.includes(key));
  return (
    <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
      {primary.map(([key, value]) => (
        <div key={key} style={{ paddingLeft: 8 }}>
          <span style={{ color: '#999' }}>{key}</span>
          <span style={{ margin: '0 6px', color: '#bbb' }}>=</span>
          <span>{formatNodeValue(value)}</span>
        </div>
      ))}
      {rest.length > 0 && (
        <details style={{ paddingLeft: 8, marginTop: 2 }}>
          <summary style={{ color: '#bbb', cursor: 'pointer' }}>其他 {rest.length} 项</summary>
          {rest.map(([key, value]) => (
            <div key={key}>
              <span style={{ color: '#999' }}>{key}</span>
              <span style={{ margin: '0 6px', color: '#bbb' }}>=</span>
              <span>{formatNodeValue(value)}</span>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

function StatusTag({ status }: { status: TraceStatus }) {
  const m = STATUS_META[status] ?? { color: 'default', text: status, icon: null };
  return <Tag color={m.color} icon={m.icon}>{m.text}</Tag>;
}

const formatMs = (ms: number | null) => {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};
const formatTime = (v?: string | null) => (v ? new Date(v).toLocaleString() : '-');
const formatNodeValue = (v: unknown): string => {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'boolean') return v ? '是' : '否';
  if (Array.isArray(v)) return v.map(String).join(', ') || '-';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};

export function TracePage() {
  const [filters, setFilters] = useState({ status: '', keyword: '' });
  const [draft, setDraft] = useState({ status: '', keyword: '' });
  const [pageNo, setPageNo] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [detailId, setDetailId] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ['traces', filters, pageNo, pageSize],
    queryFn: () => traceApi.list({ status: filters.status || undefined, keyword: filters.keyword || undefined, pageNo, pageSize }),
    refetchInterval: 10_000,
  });

  const stats = useQuery({
    queryKey: ['trace-stats'],
    queryFn: traceApi.statistics,
    refetchInterval: 15_000,
  });

  const detail = useQuery({
    queryKey: ['trace-detail', detailId],
    queryFn: () => traceApi.get(detailId!),
    enabled: !!detailId,
    refetchInterval: (q) => q.state.data?.status === 'RUNNING' ? 3000 : false,
  });

  const applyFilters = () => { setPageNo(1); setFilters(draft); };
  const resetFilters = () => { setDraft({ status: '', keyword: '' }); setFilters({ status: '', keyword: '' }); setPageNo(1); };

  const data = list.data;
  const d = detail.data;
  const st = stats.data;

  return (
    <>
      <PageHeader title="RAG Trace" description="查看每次问答的完整链路追踪" extra={
        <Button icon={<ReloadOutlined />} onClick={() => void list.refetch()} loading={list.isFetching}>刷新</Button>
      } />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={5}><Card><Statistic title="总调用" value={st?.totalCount ?? 0} loading={stats.isLoading} /></Card></Col>
        <Col span={5}><Card><Statistic title="成功率" value={st ? `${(st.successRate * 100).toFixed(1)}%` : '-'} loading={stats.isLoading} /></Card></Col>
        <Col span={5}><Card><Statistic title="平均延迟" value={st ? formatMs(st.avgLatencyMs) : '-'} loading={stats.isLoading} /></Card></Col>
        <Col span={4}><Card><Statistic title="降级" value={st?.degradedCount ?? 0} valueStyle={{ color: st?.degradedCount ? '#faad14' : undefined }} loading={stats.isLoading} /></Card></Col>
        <Col span={5}><Card><Statistic title="失败" value={st?.failedCount ?? 0} valueStyle={{ color: st?.failedCount ? '#ff4d4f' : undefined }} loading={stats.isLoading} /></Card></Col>
      </Row>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <Select allowClear placeholder="全部状态" style={{ width: 130 }} value={draft.status || undefined}
            onChange={(v) => setDraft((d) => ({ ...d, status: v ?? '' }))}
            options={Object.entries(STATUS_META).map(([k, v]) => ({ value: k, label: v.text }))} />
          <Input.Search placeholder="搜索问题或 Request ID" style={{ width: 280 }} value={draft.keyword}
            onChange={(e) => setDraft((d) => ({ ...d, keyword: e.target.value }))}
            onSearch={applyFilters} enterButton />
          <Button onClick={applyFilters}>查询</Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>
      </Card>

      <Table<RagTraceListItem> rowKey="id" loading={list.isLoading} dataSource={data?.records}
        pagination={{ current: pageNo, pageSize, total: data?.total ?? 0, showSizeChanger: true,
          onChange: (p, s) => { setPageNo(p); setPageSize(s); } }}
        onRow={(r) => ({ onClick: () => setDetailId(r.id), style: { cursor: 'pointer' } })}
        columns={[
          { title: '问题', dataIndex: 'question', width: 240, ellipsis: true, render: (v) => v ?? '-' },
          { title: '用户', dataIndex: 'username', width: 100, render: (v?: string) => v ?? '-' },
          { title: '意图', dataIndex: 'intent', width: 100, render: (v) => v ?? '-' },
          { title: '状态', dataIndex: 'status', width: 90, render: (v: TraceStatus) => <StatusTag status={v} /> },
          { title: '耗时', dataIndex: 'latencyMs', width: 90, render: formatMs },
          { title: '时间', dataIndex: 'createdAt', width: 170, render: formatTime },
        ]}
      />

      <Drawer width={720} title={`Trace ${d?.id ?? ''}`} open={!!detailId} onClose={() => setDetailId(null)}>
        {detail.isLoading ? <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div> :
         detail.isError ? <div style={{ textAlign: 'center', padding: 40, color: 'red' }}>加载失败</div> :
         d ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="状态"><StatusTag status={d.status} /></Descriptions.Item>
              <Descriptions.Item label="延迟">{formatMs(d.latencyMs)}</Descriptions.Item>
              <Descriptions.Item label="Token 输入">{d.tokenUsage?.inputTokens ?? 0}</Descriptions.Item>
              <Descriptions.Item label="Token 输出">{d.tokenUsage?.outputTokens ?? 0}</Descriptions.Item>
              <Descriptions.Item label="开始">{formatTime(d.startedAt)}</Descriptions.Item>
              <Descriptions.Item label="结束">{formatTime(d.finishedAt)}</Descriptions.Item>
              {d.errorMessage && <Descriptions.Item label="错误" span={2}><Typography.Text type="danger">{d.errorMessage}</Typography.Text></Descriptions.Item>}
              {d.degradedReasons.length > 0 && <Descriptions.Item label="降级原因" span={2}>
                {d.degradedReasons.map((r, i) => <Tag key={i} color="warning">{r}</Tag>)}
              </Descriptions.Item>}
            </Descriptions>

            <Typography.Title level={5}>执行节点</Typography.Title>
            {(() => {
              const groups = GROUP_ORDER
                .map((g) => ({
                  group: g,
                  nodes: d.nodes.filter((n) => (NODE_META[n.name]?.group ?? 'query') === g),
                }))
                .filter((x) => x.nodes.length > 0);
              return groups.map(({ group, nodes }) => (
                <Collapse
                  key={group}
                  ghost
                  style={{ marginBottom: 8 }}
                  defaultActiveKey={group === 'retrieval' || group === 'generation' ? [group] : []}
                  items={[{
                    key: group,
                    label: (
                      <Space>
                        <Typography.Text strong>{GROUP_TITLES[group]}</Typography.Text>
                        <Tag color="blue">{nodes.length}</Tag>
                      </Space>
                    ),
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }} size="small">
                        {nodes.map((n: TraceNode) => {
                          const meta = NODE_META[n.name];
                          return (
                            <Card key={`${n.name}-${n.startedAt}`} size="small">
                              <Space direction="vertical" style={{ width: '100%' }}>
                                <Space wrap>
                                  <Typography.Text strong>{meta?.label ?? n.name}</Typography.Text>
                                  {meta && <Tag color="geekblue">{n.name}</Tag>}
                                  <Tag color={NODE_COLORS[n.status] ?? 'blue'}>{n.status}</Tag>
                                  <Typography.Text type="secondary">{formatMs(n.latencyMs)}</Typography.Text>
                                  {n.status === 'SKIPPED' && <StopOutlined style={{ color: '#999' }} />}
                                </Space>
                                {Object.keys(n.inputSummary).length > 0 && (
                                  <div style={{ marginTop: 4 }}>
                                    <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 2 }}>输入</div>
                                    <NodeSummary summary={n.inputSummary} keys={meta?.inputKeys} />
                                  </div>
                                )}
                                {Object.keys(n.outputSummary).length > 0 && (
                                  <div style={{ marginTop: 4 }}>
                                    <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 2 }}>输出</div>
                                    <NodeSummary summary={n.outputSummary} keys={meta?.outputKeys} />
                                  </div>
                                )}
                                {n.errorMessage && (
                                  n.status === 'SKIPPED'
                                    ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>跳过原因: {n.errorMessage}</Typography.Text>
                                    : <Typography.Text type="danger" style={{ fontSize: 12 }}>错误: {n.errorMessage}</Typography.Text>
                                )}
                              </Space>
                            </Card>
                          );
                        })}
                      </Space>
                    ),
                  }]}
                />
              ));
            })()}
          </Space>
        ) : null}
      </Drawer>
    </>
  );
}
