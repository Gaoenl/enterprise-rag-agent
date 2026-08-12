import { useState } from 'react';
import { ExperimentOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Form,
  InputNumber,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { evaluationApi } from '../api/evaluation';
import { kbApi } from '../api/modules';
import { PageHeader } from '../components/PageHeader';
import type {
  EvaluationCreateRequest,
  EvaluationCandidate,
  EvaluationDetail,
  EvaluationSummary,
} from '../types/evaluation';
import { RetrievalDebugPage } from './RetrievalDebugPage';


const experimentOptions = [
  { label: '向量检索（无重写）', value: 'VECTOR' },
  { label: '关键词检索（无重写）', value: 'KEYWORD' },
  { label: '混合检索（无重写）', value: 'HYBRID' },
  { label: '混合检索 + Rerank（无重写）', value: 'HYBRID_RERANK' },
  { label: '混合检索 + Rewrite', value: 'HYBRID_REWRITE' },
  { label: '混合检索 + Rewrite + Rerank', value: 'HYBRID_REWRITE_RERANK' },
  { label: '混合检索 + 多查询', value: 'HYBRID_MULTI_QUERY' },
  { label: '混合检索 + 多查询 + Rewrite', value: 'HYBRID_MULTI_QUERY_REWRITE' },
  { label: '混合检索 + 多查询 + Rewrite + Rerank', value: 'HYBRID_MULTI_QUERY_REWRITE_RERANK' },
];

const percentage = (value: number) => `${(value * 100).toFixed(1)}%`;
const optionalPercentage = (value: number | null) => value === null ? '-' : percentage(value);

/** RAG 测评总页面，内部保留单问题检索调试。 */
export function RagEvaluationPage() {
  return (
    <>
      <PageHeader
        title="RAG 测评"
        description="批量评估检索质量，并保留单问题全链路调试能力"
      />
      <Tabs
        defaultActiveKey="evaluation"
        items={[
          {
            key: 'evaluation',
            label: '批量测评',
            children: <EvaluationPanel />,
          },
          {
            key: 'debug',
            label: '检索调试',
            children: <RetrievalDebugPage embedded />,
          },
        ]}
      />
    </>
  );
}

function EvaluationPanel() {
  const { message } = App.useApp();
  const [form] = Form.useForm<EvaluationCreateRequest>();
  const [runId, setRunId] = useState<string>();
  const datasetCode = Form.useWatch('datasetCode', form);

  const knowledgeBases = useQuery({
    queryKey: ['kb', 'rag-evaluation'],
    queryFn: () => kbApi.page({ pageNo: 1, pageSize: 100 }),
  });

  const createMutation = useMutation({
    mutationFn: evaluationApi.create,
    onSuccess: (run) => {
      setRunId(run.runId);
      message.success('评测任务已创建');
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : '创建评测任务失败'),
  });

  const statusQuery = useQuery({
    queryKey: ['rag-evaluation', runId],
    queryFn: () => evaluationApi.getStatus(runId!),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'SUCCESS' || status === 'FAILED' ? false : 2000;
    },
  });

  const resultQuery = useQuery({
    queryKey: ['rag-evaluation-result', runId],
    queryFn: () => evaluationApi.getResult(runId!),
    enabled: Boolean(runId) && statusQuery.data?.status === 'SUCCESS',
  });

  const running = statusQuery.data?.status === 'PENDING'
    || statusQuery.data?.status === 'RUNNING';

  const submitEvaluation = (values: EvaluationCreateRequest) => {
    const includesHybridExperiment = values.experiments.some((item) =>
      item.startsWith('HYBRID'));
    if (
      includesHybridExperiment
      && values.vectorWeight === 0
      && values.keywordWeight === 0
    ) {
      message.error('向量权重和关键词权重不能同时为 0');
      return;
    }
    createMutation.mutate(values);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="评测配置" size="small">
        <Form<EvaluationCreateRequest>
          form={form}
          layout="vertical"
          initialValues={{
            datasetCode: 'CRUD_RAG_V1',
            experiments: ['VECTOR', 'KEYWORD', 'HYBRID', 'HYBRID_RERANK'],
            vectorWeight: 0.5,
            keywordWeight: 1,
          }}
          onFinish={submitEvaluation}
        >
          <Space size={24} align="start" wrap>
            <Form.Item
              name="knowledgeBaseId"
              label="评测知识库"
              rules={[{ required: true, message: '请选择评测知识库' }]}
              style={{ width: 320 }}
            >
              <Select
                showSearch
                optionFilterProp="label"
                placeholder="选择已完成向量化的知识库"
                loading={knowledgeBases.isLoading}
                options={knowledgeBases.data?.records.map((item) => ({
                  value: item.id,
                  label: `${item.name}（${Number(item.documentCount ?? 0)} 个文档）`,
                }))}
              />
            </Form.Item>
            <Form.Item name="datasetCode" label="评测数据集" style={{ width: 220 }}>
              <Select
                options={[
                  { value: 'CRUD_RAG_V1', label: 'CRUD-RAG V1（随机负样本）' },
                  { value: 'CRUD_RAG_V2', label: 'CRUD-RAG V2（Hard Negative）' },
                ]}
              />
            </Form.Item>
          </Space>

          <Form.Item
            name="experiments"
            label="检索实验"
            rules={[{ required: true, message: '至少选择一种实验' }]}
          >
            <Checkbox.Group options={experimentOptions} />
          </Form.Item>

          <Space size={24} align="start" wrap>
            <Form.Item
              name="vectorWeight"
              label="向量权重"
              tooltip="向量召回排名在 Weighted RRF 中的权重"
              rules={[{ required: true, message: '请输入向量权重' }]}
            >
              <InputNumber min={0} max={10} step={0.1} precision={2} />
            </Form.Item>
            <Form.Item
              name="keywordWeight"
              label="关键词权重"
              tooltip="关键词召回排名在 Weighted RRF 中的权重"
              rules={[{ required: true, message: '请输入关键词权重' }]}
            >
              <InputNumber min={0} max={10} step={0.1} precision={2} />
            </Form.Item>
          </Space>

          {datasetCode === 'CRUD_RAG_V2' && (
            <Alert
              type="warning"
              showIcon
              message="V2 必须配套使用已导入 crud_v2/documents 全部 1000 篇文档的独立知识库"
              description="选择原 V1 知识库不会包含 Hard Negative，测评结果仍可能保持不变。"
              style={{ marginBottom: 16 }}
            />
          )}

          <Button
            type="primary"
            htmlType="submit"
            icon={<ExperimentOutlined />}
            loading={createMutation.isPending}
            disabled={running}
          >
            开始测评
          </Button>
        </Form>
      </Card>

      {statusQuery.data && (
        <Card title="任务进度" size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <Tag color={statusQuery.data.status === 'FAILED' ? 'error' : 'processing'}>
                {statusQuery.data.status}
              </Tag>
              {statusQuery.data.currentExperiment && (
                <span>当前实验：{statusQuery.data.currentExperiment}</span>
              )}
              <span>
                {statusQuery.data.completedCases} / {statusQuery.data.totalCases} Cases
              </span>
            </Space>
            <Progress
              percent={statusQuery.data.progress}
              status={statusQuery.data.status === 'FAILED' ? 'exception' : undefined}
            />
            {statusQuery.data.errorMessage && (
              <Alert type="error" showIcon message={statusQuery.data.errorMessage} />
            )}
          </Space>
        </Card>
      )}

      {resultQuery.data && (
        <>
          <Card title="指标对比" size="small">
            <Table<EvaluationSummary>
              rowKey="experiment"
              pagination={false}
              dataSource={resultQuery.data.summaries}
              columns={[
                { title: '实验', dataIndex: 'experiment' },
                { title: '文档 Hit@1', dataIndex: 'hitAt1', render: percentage },
                { title: '文档 Hit@3', dataIndex: 'hitAt3', render: percentage },
                { title: '文档 Hit@5', dataIndex: 'hitAt5', render: percentage },
                { title: '文档 Hit@8', dataIndex: 'hitAt8', render: percentage },
                { title: '文档 MRR', dataIndex: 'mrr', render: (v) => Number(v).toFixed(4) },
                {
                  title: '证据分块 Hit@5',
                  dataIndex: 'chunkHitAt5',
                  render: optionalPercentage,
                },
                {
                  title: '平均耗时',
                  dataIndex: 'averageLatencyMillis',
                  render: (v) => `${Number(v).toFixed(0)} ms`,
                },
                {
                  title: 'P95',
                  dataIndex: 'p95LatencyMillis',
                  render: (v) => `${Number(v).toFixed(0)} ms`,
                },
                { title: '失败', dataIndex: 'failedCount' },
              ]}
            />
          </Card>

          <Card title="Case 明细" size="small">
            <Table<EvaluationDetail>
              rowKey={(item) => `${item.experiment}-${item.caseId}`}
              dataSource={resultQuery.data.details}
              pagination={{ pageSize: 10 }}
              expandable={{
                expandedRowRender: (item) => <CaseDiagnosis detail={item} />,
              }}
              columns={[
                { title: '实验', dataIndex: 'experiment', width: 150 },
                { title: '问题', dataIndex: 'question', ellipsis: true },
                {
                  title: '文档 Hit@5',
                  dataIndex: 'hitAt5',
                  width: 90,
                  render: (value) => (
                    <Tag color={value ? 'success' : 'error'}>{value ? '命中' : '未命中'}</Tag>
                  ),
                },
                { title: '首个相关文档排名', dataIndex: 'firstRelevantRank', width: 145 },
                {
                  title: '耗时',
                  dataIndex: 'latencyMillis',
                  width: 110,
                  render: (value) => `${Number(value).toLocaleString()} ms`,
                },
                {
                  title: '异常',
                  dataIndex: 'error',
                  ellipsis: true,
                  render: (value) => value ?? '-',
                },
              ]}
            />
          </Card>
        </>
      )}
    </Space>
  );
}

/** 展示一次检索的真实查询和候选分块，避免只看汇总指标。 */
function CaseDiagnosis({ detail }: { detail: EvaluationDetail }) {
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="语义查询">
          {detail.semanticQuery}
        </Descriptions.Item>
        <Descriptions.Item label="查询改写">
          {detail.rewriteApplied ? '已启用' : '未启用'}
        </Descriptions.Item>
        <Descriptions.Item label="关键词">
          <Space size={[4, 4]} wrap>
            {detail.keywords.length > 0
              ? detail.keywords.map((keyword) => <Tag key={keyword}>{keyword}</Tag>)
              : '-'}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="正确文档">
          {detail.goldDocumentNames.join('、')}
        </Descriptions.Item>
        <Descriptions.Item label="证据分块指标">
          {detail.evidenceEvaluated
            ? `首个相关分块排名：${detail.firstRelevantChunkRank ?? '未命中'}`
            : '当前数据集没有人工证据标注，暂不计算'}
        </Descriptions.Item>
      </Descriptions>

      <Typography.Text strong>Top 8 实际召回分块</Typography.Text>
      <Table<EvaluationCandidate>
        size="small"
        rowKey={(item) => `${item.chunkId}`}
        pagination={false}
        dataSource={detail.retrievedCandidates}
        columns={[
          { title: '文档', dataIndex: 'documentName', width: 240, ellipsis: true },
          { title: '分块', dataIndex: 'chunkIndex', width: 70 },
          { title: '向量分', dataIndex: 'vectorScore', width: 90, render: score },
          { title: '关键词分', dataIndex: 'keywordScore', width: 90, render: score },
          { title: '融合分', dataIndex: 'fusionScore', width: 90, render: score },
          { title: '重排分', dataIndex: 'rerankScore', width: 90, render: score },
          { title: '内容', dataIndex: 'content', ellipsis: true },
        ]}
      />
    </Space>
  );
}

function score(value: number | null) {
  return value === null ? '-' : Number(value).toFixed(4);
}
