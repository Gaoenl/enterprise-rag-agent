import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Collapse, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { kbApi, modelApi } from '../api/modules';
import { PageHeader } from '../components/PageHeader';
import type { DomainCode, KnowledgeBase, ModelConfig, PipelineConfig } from '../types/api';

const CHUNKER_OPTIONS = [
  { value: 'recursive', label: '递归切分' },
  { value: 'fixed', label: '固定长度切分' },
  { value: 'paragraph', label: '段落切分' },
];

// 数据库 kb_document_chunk.embedding 列维度（pgvector 固定维度）。
const DB_EMBEDDING_DIMENSION = 1536;

const DOMAIN_OPTIONS: { value: DomainCode; label: string }[] = [
  { value: 'EXPENSE', label: '报销' },
  { value: 'HR', label: '人事' },
  { value: 'CONTRACT', label: '合同' },
  { value: 'POLICY', label: '制度' },
  { value: 'GENERAL', label: '通用' },
];

/** 从模型配置解析支持的维度，兼容 {"dimensions":[...]} 与 {"dimension":N}。 */
function parseDimensions(model: ModelConfig): number[] {
  if (model.dimensions?.length) return model.dimensions;
  if (!model.parameters) return [];
  try {
    const params = JSON.parse(model.parameters) as {
      dimensions?: number[];
      dimension?: number;
    };
    if (Array.isArray(params.dimensions)) return params.dimensions;
    if (typeof params.dimension === 'number') return [params.dimension];
  } catch {
    // 忽略解析失败，返回空列表
  }
  return [];
}

type FormValue = Pick<KnowledgeBase, 'name' | 'description' | 'visibility'> & {
  domainCode: DomainCode;
  chunkType: string;
  chunkSize: number;
  chunkOverlap: number;
  embeddingModel: string;
  embeddingBatchSize: number;
};

/** 将表单值序列化为 PipelineConfig */
function toPipelineConfig(v: FormValue): PipelineConfig {
  // 下拉选项 value 编码为 "modelCode::dimension"，提交时拆回。
  const [model, dim] = v.embeddingModel ? v.embeddingModel.split('::') : [];
  return {
    chunkType: v.chunkType || 'recursive',
    chunkSize: v.chunkSize || 800,
    chunkOverlap: v.chunkOverlap ?? 100,
    embeddingModel: model || undefined,
    embeddingDimension: dim ? Number(dim) : undefined,
    embeddingBatchSize: v.embeddingBatchSize || undefined,
  };
}

/** 将后端 PipelineConfig 反序列化为表单默认值 */
function fromPipelineConfig(c?: PipelineConfig | null): Partial<FormValue> {
  if (!c) return {};
  return {
    chunkType: c.chunkType ?? 'recursive',
    chunkSize: c.chunkSize ?? 800,
    chunkOverlap: c.chunkOverlap ?? 100,
    embeddingModel: c.embeddingModel
      ? `${c.embeddingModel}::${c.embeddingDimension ?? DB_EMBEDDING_DIMENSION}`
      : '',
    embeddingBatchSize: c.embeddingBatchSize ?? 10,
  };
}
export function KnowledgePage() {
  const nav = useNavigate(),
    qc = useQueryClient(),
    { message } = App.useApp();
  const [page, setPage] = useState(1),
    [search, setSearch] = useState(''),
    [keyword, setKeyword] = useState(''),
    [editing, setEditing] = useState<KnowledgeBase | null>(null),
    [open, setOpen] = useState(false);
  const [form] = Form.useForm<FormValue>();
  const embeddingModels = useQuery({
    queryKey: ['models', 'EMBEDDING'],
    queryFn: () => modelApi.listByType('EMBEDDING'),
  });
  // 下拉选项 = 模型 × 维度组合："模型名 (N 维)"。
  const embeddingOptions = useMemo(
    () =>
      (embeddingModels.data ?? []).flatMap((model) =>
        parseDimensions(model).map((dim) => ({
          value: `${model.modelCode}::${dim}`,
          label: `${model.modelName} (${dim}d)`,
          disabled: dim !== DB_EMBEDDING_DIMENSION,
          title:
            dim !== DB_EMBEDDING_DIMENSION
              ? `当前数据库列维度为 ${DB_EMBEDDING_DIMENSION}，需迁移后才能使用`
              : undefined,
        })),
      ),
    [embeddingModels.data],
  );
  // 搜索防抖 300ms
  useEffect(() => {
    const timer = setTimeout(() => setKeyword(search), 300);
    return () => clearTimeout(timer);
  }, [search]);
  const query = useQuery({
    queryKey: ['kb', page, keyword],
    queryFn: () => kbApi.page({ pageNo: page, pageSize: 10, keyword: keyword || undefined }),
  });
  const save = useMutation({
    mutationFn: (v: FormValue) => {
      const payload = { ...v, pipelineConfig: toPipelineConfig(v) };
      return editing ? kbApi.update(editing.id, payload) : kbApi.create(payload);
    },
    onSuccess: (result) => {
      message.success(editing ? '知识库已更新' : '知识库已创建');
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ['kb'] });
      if (!editing) nav(`/admin/knowledge/${result.id}/documents`);
    },
    onError: (error) => message.error(error.message),
  });
  const remove = useMutation({
    mutationFn: kbApi.remove,
    onSuccess: () => {
      message.success('知识库已删除');
      void qc.invalidateQueries({ queryKey: ['kb'] });
    },
    onError: (error) => message.error(error.message),
  });
  const show = (item?: KnowledgeBase) => {
    setEditing(item ?? null);
    form.setFieldsValue({
      name: '',
      description: '',
      visibility: 'PRIVATE',
      domainCode: 'GENERAL',
      ...item,
      ...fromPipelineConfig(item?.chunkStrategy),
    });
    setOpen(true);
  };
  return (
    <>
      <PageHeader
        title="知识库"
        description="组织企业知识资产，管理文档与索引"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => show()}>
            新建知识库
          </Button>
        }
      />
      <div className="filter-bar">
        <Input.Search
          allowClear
          placeholder="搜索知识库"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          onSearch={(v) => setKeyword(v)}
          style={{ width: 320 }}
        />
      </div>
      {query.isError && (
        <Alert
          className="page-alert"
          type="error"
          showIcon
          message="知识库列表加载失败"
          description={`${query.error.message}。仍可新建知识库，成功后将直接进入文档页。`}
        />
      )}
      <Table
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.records}
        pagination={{
          current: page,
          pageSize: 10,
          // 后端 total 异常为 0 时，使用当前已返回记录数兜底，避免分页器显示空数据。
          total: Math.max(query.data?.total ?? 0, query.data?.records.length ?? 0),
          onChange: setPage,
        }}
        columns={[
          {
            title: '知识库',
            dataIndex: 'name',
            render: (v: string, r) => (
              <Button type="link" onClick={() => nav(`/admin/knowledge/${r.id}/documents`)}>
                {v}
              </Button>
            ),
          },
          { title: '说明', dataIndex: 'description', ellipsis: true },
          {
            title: '可见性',
            dataIndex: 'visibility',
            render: (v) => <Tag color={v === 'PRIVATE' ? 'blue' : 'green'}>{v}</Tag>,
          },
          {
            title: '业务域',
            dataIndex: 'domainCode',
            render: (v: DomainCode) => <Tag>{v ?? 'GENERAL'}</Tag>,
          },
          {
            title: '文档数',
            dataIndex: 'documentCount',
            width: 100,
            render: (value) => Number(value ?? 0).toLocaleString(),
          },
          {
            title: '更新时间',
            dataIndex: 'updatedAt',
            render: (v) => new Date(v).toLocaleString(),
          },
          {
            title: '操作',
            render: (_, r) => (
              <Space>
                <Button
                  icon={<RightOutlined />}
                  onClick={() => nav(`/admin/knowledge/${r.id}/documents`)}
                >
                  文档
                </Button>
                <Button icon={<EditOutlined />} onClick={() => show(r)} />
                <Popconfirm title="确认删除该知识库？" onConfirm={() => remove.mutate(r.id)}>
                  <Button danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? '编辑知识库' : '新建知识库'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="visibility" label="可见性" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'PRIVATE', label: '私有' },
                { value: 'TENANT', label: '租户可见' },
              ]}
            />
          </Form.Item>
          <Form.Item name="domainCode" label="业务域" rules={[{ required: true }]}>
            <Select options={DOMAIN_OPTIONS} />
          </Form.Item>
          <Collapse
            ghost
            items={[{
              key: 'pipeline',
              label: '入库流水线配置',
              children: (
                <>
                  <Form.Item name="chunkType" label="切分方式">
                    <Select options={CHUNKER_OPTIONS} />
                  </Form.Item>
                  <Space style={{ width: '100%' }} size="middle">
                    <Form.Item name="chunkSize" label="分块大小（字符）" style={{ flex: 1 }}>
                      <InputNumber min={100} max={5000} step={50} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="chunkOverlap" label="重叠大小（字符）" style={{ flex: 1 }}>
                      <InputNumber min={0} max={500} step={10} style={{ width: '100%' }} />
                    </Form.Item>
                  </Space>
                  <Form.Item
                    name="embeddingModel"
                    label="Embedding 模型（维度）"
                    extra="维度随所选模型自动确定，需与数据库列维度一致"
                  >
                    <Select
                      allowClear
                      placeholder="留空使用全局默认"
                      loading={embeddingModels.isLoading}
                      options={embeddingOptions}
                      notFoundContent={
                        embeddingModels.isError ? '模型列表加载失败' : undefined
                      }
                    />
                  </Form.Item>
                  <Form.Item name="embeddingBatchSize" label="批处理大小">
                    <InputNumber min={1} max={50} style={{ width: '100%' }} placeholder="留空使用默认" />
                  </Form.Item>
                </>
              ),
            }]}
          />
        </Form>
      </Modal>
    </>
  );
}
