import { useEffect, useMemo, useRef } from 'react';
import { ExperimentOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { kbApi } from '../api/modules';
import { retrievalApi } from '../api/retrieval';
import { PackedContextViewer } from '../components/retrieval/PackedContextViewer';
import { RetrievalResultTable } from '../components/retrieval/RetrievalResultTable';
import { PageHeader } from '../components/PageHeader';
import type { RetrievalDebugRequest, RetrievalTimings } from '../types/retrieval';

const modeOptions = [
  { label: '向量检索', value: 'VECTOR' },
  { label: '关键词检索', value: 'KEYWORD' },
  { label: '混合检索', value: 'HYBRID' },
];

const formatMillis = (value: number | string) => `${Number(value).toLocaleString()} ms`;

export function RetrievalDebugPage(
  { embedded = false }: { embedded?: boolean } = {},
) {
  const { message } = App.useApp();
  const [form] = Form.useForm<RetrievalDebugRequest>();
  const mode = Form.useWatch('mode', form) ?? 'HYBRID';

  const knowledgeBases = useQuery({
    queryKey: ['kb', 'retrieval-debug'],
    queryFn: () => kbApi.page({ pageNo: 1, pageSize: 100 }),
  });

  // 检索默认参数以服务端配置为唯一真相，加载完成后填充表单。
  const retrievalConfig = useQuery({
    queryKey: ['retrieval', 'config'],
    queryFn: retrievalApi.getConfig,
  });

  const configApplied = useRef(false);
  useEffect(() => {
    if (retrievalConfig.data && !configApplied.current) {
      configApplied.current = true;
      form.setFieldsValue({
        vectorTopK: retrievalConfig.data.vectorTopK,
        keywordTopK: retrievalConfig.data.keywordTopK,
        fusionTopK: retrievalConfig.data.fusionTopK,
        finalTopK: retrievalConfig.data.finalTopK,
        rrfK: retrievalConfig.data.rrfK,
        vectorWeight: retrievalConfig.data.vectorWeight,
        keywordWeight: retrievalConfig.data.keywordWeight,
        enableMultiQuery: retrievalConfig.data.multiQueryEnabled,
      });
    }
  }, [retrievalConfig.data, form]);

  const debugMutation = useMutation({
    mutationFn: retrievalApi.debug,
    onSuccess: () => message.success('检索调试完成'),
    onError: (error) => message.error(error instanceof Error ? error.message : '检索调试失败'),
  });

  const result = debugMutation.data;
  const timingItems = useMemo(() => {
    if (!result) return [];

    const timings: Array<[string, keyof RetrievalTimings]> = [
      ['问题改写', 'rewriteMillis'],
      ['向量检索', 'vectorMillis'],
      ['关键词检索', 'keywordMillis'],
      ['RRF 融合', 'fusionMillis'],
      ['Rerank', 'rerankMillis'],
      ['上下文打包', 'packingMillis'],
      ['总耗时', 'totalMillis'],
    ];

    return timings.map(([label, key]) => ({ label, value: result.timings[key] }));
  }, [result]);

  const submit = (values: RetrievalDebugRequest) => {
    if (
      values.mode === 'HYBRID'
      && values.vectorWeight === 0
      && values.keywordWeight === 0
    ) {
      message.error('向量权重和关键词权重不能同时为 0');
      return;
    }
    debugMutation.mutate({
      ...values,
      question: values.question.trim(),
    });
  };

  return (
    <>
      {!embedded && (
        <PageHeader
          title="检索调试台"
          description="逐阶段检查查询改写、召回、融合、重排和最终上下文"
        />
      )}

      <Card className="retrieval-form-card">
        <Form<RetrievalDebugRequest>
          form={form}
          layout="vertical"
          initialValues={{
            mode: 'HYBRID',
            enableRewrite: true,
            enableRerank: true,
            vectorTopK: 30,
            keywordTopK: 30,
            fusionTopK: 20,
            finalTopK: 15,
            rrfK: 60,
            vectorWeight: 1,
            keywordWeight: 1,
            enableMultiQuery: true,
          }}
          onFinish={submit}
        >
          <Row gutter={18}>
            <Col span={10}>
              <Form.Item
                name="knowledgeBaseId"
                label="知识库（不选则检索全部）"
              >
                <Select
                  showSearch
                  allowClear
                  optionFilterProp="label"
                  placeholder="不选择则检索当前租户全部知识库"
                  loading={knowledgeBases.isLoading}
                  options={knowledgeBases.data?.records.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={14}>
              <Form.Item name="mode" label="检索模式">
                <Segmented block options={modeOptions} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="question"
            label="用户问题"
            rules={[
              { required: true, whitespace: true, message: '请输入需要检索的问题' },
              { max: 4000, message: '问题不能超过 4000 个字符' },
            ]}
          >
            <Input.TextArea
              rows={4}
              showCount
              maxLength={4000}
              placeholder="输入问题，观察每一个检索阶段如何处理它"
            />
          </Form.Item>

          <div className="retrieval-switches">
            <Form.Item name="enableRewrite" valuePropName="checked" label="查询改写">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Form.Item name="enableRerank" valuePropName="checked" label="Rerank">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Form.Item name="enableMultiQuery" valuePropName="checked" label="多查询召回">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
          </div>

          <Collapse
            ghost
            className="retrieval-advanced"
            items={[
              {
                key: 'advanced',
                label: '高级检索参数',
                // 即使面板未展开，也要注册内部 Form 字段并提交默认值。
                forceRender: true,
                children: (
                  <Row gutter={16}>
                    <Col span={5}>
                      <Form.Item name="vectorTopK" label="Vector TopK">
                        <InputNumber min={1} max={100} disabled={mode === 'KEYWORD'} />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item name="keywordTopK" label="Keyword TopK">
                        <InputNumber min={1} max={100} disabled={mode === 'VECTOR'} />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item name="fusionTopK" label="Fusion TopK">
                        <InputNumber min={1} max={100} disabled={mode !== 'HYBRID'} />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item name="finalTopK" label="Final TopK">
                        <InputNumber min={1} max={50} />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item name="rrfK" label="RRF K">
                        <InputNumber min={1} max={1000} disabled={mode !== 'HYBRID'} />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item name="vectorWeight" label="向量权重">
                        <InputNumber
                          min={0}
                          max={10}
                          step={0.1}
                          precision={2}
                          disabled={mode !== 'HYBRID'}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Form.Item name="keywordWeight" label="关键词权重">
                        <InputNumber
                          min={0}
                          max={10}
                          step={0.1}
                          precision={2}
                          disabled={mode !== 'HYBRID'}
                        />
                      </Form.Item>
                    </Col>
                  </Row>
                ),
              },
            ]}
          />

          <Space>
            <Button
              type="primary"
              htmlType="submit"
              icon={<SearchOutlined />}
              loading={debugMutation.isPending}
            >
              执行检索
            </Button>
            <Button
              onClick={() => {
                form.resetFields();
                debugMutation.reset();
              }}
            >
              重置
            </Button>
          </Space>
        </Form>
      </Card>

      {!result && !debugMutation.isPending && (
        <div className="retrieval-empty">
          <Empty image={<ExperimentOutlined />} description="配置参数并执行一次检索调试" />
        </div>
      )}

      {result && (
        <>
          {(result.degraded || result.warnings.length > 0) && (
            <Alert
              className="section-card"
              type="warning"
              showIcon
              message={result.degraded ? '本次检索发生降级' : '检索提示'}
              description={result.warnings.join('；')}
            />
          )}

          <div className="retrieval-query-summary section-card">
            <div>
              <Typography.Text type="secondary">语义查询</Typography.Text>
              <Typography.Paragraph strong>{result.semanticQuery}</Typography.Paragraph>
            </div>
            <div>
              <Typography.Text type="secondary">关键词</Typography.Text>
              <div className="retrieval-keywords">
                {result.keywords.length > 0
                  ? result.keywords.map((keyword) => <Tag key={keyword}>{keyword}</Tag>)
                  : <Typography.Text type="secondary">未提取关键词</Typography.Text>}
              </div>
            </div>
            {(result.alternativeQueries?.length ?? 0) > 0 && (
              <div>
                <Typography.Text type="secondary">子查询</Typography.Text>
                <div className="retrieval-keywords">
                  {(result.alternativeQueries ?? []).map((query) => (
                    <Tag key={query} color="purple">{query}</Tag>
                  ))}
                </div>
              </div>
            )}
            <Space wrap>
              <Tag color="blue">{result.mode}</Tag>
              <Tag color={result.rewriteApplied ? 'success' : 'default'}>Rewrite</Tag>
              <Tag color={result.rerankApplied ? 'success' : 'default'}>Rerank</Tag>
              {(result.vectorMergedCount ?? 0) > 0 && (
                <Tag color="cyan">向量合并 {result.vectorMergedCount ?? 0}</Tag>
              )}
            </Space>
          </div>

          <div className="retrieval-timing-grid">
            {timingItems.map((item) => (
              <div className={item.label === '总耗时' ? 'is-total' : ''} key={item.label}>
                <Statistic title={item.label} value={formatMillis(item.value)} />
              </div>
            ))}
          </div>

          <Card title="阶段结果" className="section-card">
            <Tabs
              items={[
                {
                  key: 'vector',
                  label: `向量检索 (${result.vectorResults.length})`,
                  children: <RetrievalResultTable results={result.vectorResults} />,
                },
                {
                  key: 'keyword',
                  label: `关键词检索 (${result.keywordResults.length})`,
                  children: <RetrievalResultTable results={result.keywordResults} />,
                },
                {
                  key: 'fusion',
                  label: `RRF 融合 (${result.fusionResults.length})`,
                  children: <RetrievalResultTable results={result.fusionResults} />,
                },
                {
                  key: 'rerank',
                  label: `Rerank (${result.rerankResults.length})`,
                  children: <RetrievalResultTable results={result.rerankResults} />,
                },
              ]}
            />
          </Card>

          <Card title="最终模型上下文" className="section-card">
            <PackedContextViewer context={result.packedContext} />
          </Card>
        </>
      )}
    </>
  );
}
