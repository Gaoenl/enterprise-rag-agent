import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, App, Button, Card, Drawer, Input, Popconfirm, Progress,
  Space, Table, Tag, Upload,
} from 'antd';
import type { UploadFile } from 'antd';
import {
  DeleteOutlined, EyeOutlined, InboxOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import { documentApi, kbApi, taskApi } from '../api/modules';
import { PageHeader } from '../components/PageHeader';
import type { DocumentChunk, DocumentParseStatus, KnowledgeDocument } from '../types/api';

const PARSE_STATUS_LABEL: Record<DocumentParseStatus, { color: string; text: string }> = {
  PENDING:    { color: 'default',    text: '排队中' },
  PROCESSING: { color: 'processing', text: '解析切分中' },
  PARSED:     { color: 'warning',    text: '已解析，等待向量化' },
  EMBEDDING:  { color: 'processing', text: '向量化中' },
  READY:      { color: 'success',    text: '处理完成' },
  FAILED:     { color: 'error',      text: '处理失败' },
};

/** 单次发给后端的最大文件数量，更多文件由前端自动拆分为后续批次。 */
const UPLOAD_BATCH_SIZE = 20;

/** 轮询任务进度（每 2 秒），直到任务进入终态 */
function useTaskPolling(documentId: string | undefined) {
  return useQuery({
    queryKey: ['task', documentId],
    queryFn: () => taskApi.getByDocument(documentId!),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'SUCCESS' || status === 'FAILED' ? false : 2000;
    },
  });
}

export function DocumentsPage() {
  const { knowledgeBaseId = '' } = useParams(),
    qc = useQueryClient(),
    { message } = App.useApp();
  const [search, setSearch] = useState(''),
    [uploadFiles, setUploadFiles] = useState<UploadFile[]>([]),
    [uploadProgress, setUploadProgress] = useState<number | null>(null),
    [uploading, setUploading] = useState(false),
    [doc, setDoc] = useState<KnowledgeDocument | null>(null),
    [trackingDocId, setTrackingDocId] = useState<string | undefined>(),
    [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);

  const kb = useQuery({
    queryKey: ['kb', knowledgeBaseId],
    queryFn: () => kbApi.get(knowledgeBaseId),
  });
  const docs = useQuery({
    queryKey: ['documents', knowledgeBaseId],
    queryFn: () => documentApi.list(knowledgeBaseId),
    enabled: Boolean(knowledgeBaseId),
    // 存在未完成文档时定时刷新状态；全部进入终态后自动停止轮询。
    refetchInterval: (query) => {
      const documents = query.state.data;
      const hasActiveDocument = documents?.some(
        (document) =>
          document.parseStatus !== 'READY' &&
          document.parseStatus !== 'FAILED',
      );

      return hasActiveDocument ? 2000 : false;
    },
  });

  const hasActiveDocuments = docs.data?.some(
    (document) =>
      document.parseStatus !== 'READY' &&
      document.parseStatus !== 'FAILED',
  ) ?? false;

  // 只查询正在执行的任务，而不是为每个文档分别发送进度请求。
  const runningTasks = useQuery({
    queryKey: ['running-tasks', knowledgeBaseId],
    queryFn: () =>
      taskApi.page({
        knowledgeBaseId,
        status: 'RUNNING',
        pageNo: 1,
        pageSize: 100,
      }),
    enabled: Boolean(knowledgeBaseId) && hasActiveDocuments,
    refetchInterval: hasActiveDocuments ? 2000 : false,
  });
  const chunks = useQuery({
    queryKey: ['chunks', doc?.id],
    queryFn: () => documentApi.chunks(doc!.id),
    enabled: Boolean(doc),
  });
  // 轮询最新上传文档的处理进度
  const taskPoll = useTaskPolling(trackingDocId);

  const filtered = useMemo(
    () => docs.data?.filter((d) => d.fileName.toLowerCase().includes(search.toLowerCase())) ?? [],
    [docs.data, search],
  );

  // 按文档 ID 建立运行中任务索引，供表格逐行展示真实进度。
  const runningTaskByDocumentId = useMemo(
    () =>
      new Map(
        runningTasks.data?.records.map(
          (task) => [task.documentId, task],
        ) ?? [],
      ),
    [runningTasks.data],
  );

  // 已完成的文档 ID 集合
  const completedIds = useMemo(
    () => new Set(filtered.filter((d) => d.parseStatus === 'READY').map((d) => d.id)),
    [filtered],
  );

  const remove = useMutation({
    mutationFn: documentApi.remove,
    onSuccess: () => {
      message.success('文档已删除');
      void qc.invalidateQueries({ queryKey: ['documents', knowledgeBaseId] });
    },
  });

  const batchRemove = useMutation({
    mutationFn: (ids: string[]) => documentApi.batchRemove(ids),
    onSuccess: () => {
      message.success('批量删除完成');
      setSelectedRowKeys([]);
      void qc.invalidateQueries({ queryKey: ['documents', knowledgeBaseId] });
    },
    onError: (e) => message.error(e instanceof Error ? e.message : '批量删除失败'),
  });

  const retryTask = useMutation({
    mutationFn: taskApi.retry,
    onSuccess: () => {
      message.success('已重新加入处理队列');
      void qc.invalidateQueries({ queryKey: ['task'] });
    },
    onError: (e) => message.error(e instanceof Error ? e.message : '重试失败'),
  });

  /**
   * 将用户选择的文件按每批 20 个串行上传。
   * 当前批次完成后才发送下一批，避免大量文件同时占用后端资源。
   */
  const upload = async () => {
    const pendingFiles = uploadFiles.flatMap((item) =>
      item.originFileObj
        ? [{ uid: item.uid, file: item.originFileObj }]
        : [],
    );

    if (pendingFiles.length === 0) {
      message.warning('请先选择需要上传的文件');
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    try {
      for (let start = 0; start < pendingFiles.length; start += UPLOAD_BATCH_SIZE) {
        // 从完整队列中取出当前批次，最多包含 20 个文件。
        const batch = pendingFiles.slice(start, start + UPLOAD_BATCH_SIZE);

        const documents = await documentApi.upload(
          knowledgeBaseId,
          batch.map((item) => item.file),
          (batchProgress) => {
            // 将当前批次进度换算为整个文件队列的总进度。
            const uploadedEquivalent = start + (batch.length * batchProgress) / 100;
            setUploadProgress(
              Math.round((uploadedEquivalent / pendingFiles.length) * 100),
            );
          },
        );

        // 当前批次成功后从待上传列表移除，后续失败时只需重试剩余文件。
        const uploadedUids = new Set(batch.map((item) => item.uid));
        setUploadFiles((current) =>
          current.filter((item) => !uploadedUids.has(item.uid)),
        );

        // 选择本批最后一个文档用于展示异步处理进度。
        const latestDocument = documents[documents.length - 1];
        if (latestDocument) {
          setTrackingDocId(latestDocument.id);
        }

        // 每批完成后刷新一次列表，让用户及时看到已登记的文档。
        await qc.invalidateQueries({ queryKey: ['documents', knowledgeBaseId] });
      }

      setUploadProgress(100);
      message.success(`${pendingFiles.length} 个文件已上传，正在后台处理`);
    } catch (e) {
      message.error(e instanceof Error ? e.message : '批量上传失败，剩余文件可重新上传');
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <PageHeader title={kb.data?.name ?? '文档管理'} description="上传文档后自动解析、切分和向量化" />
      {(kb.isError || docs.isError) && (
        <Alert className="page-alert" type="error" showIcon
          message="文档数据加载失败" description={(kb.error ?? docs.error)?.message} />
      )}

      {/* 正在处理 / 已查看进度的任务 */}
      {taskPoll.data && (() => {
        const docStatus = docs.data?.find(d => d.id === trackingDocId)?.parseStatus;
        const statusLabel = docStatus ? PARSE_STATUS_LABEL[docStatus as DocumentParseStatus] : null;
        return (
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <span>任务进度：</span>
                <Progress
                  percent={taskPoll.data.progress}
                  size="small"
                  style={{ width: 200 }}
                  status={taskPoll.data.status === 'FAILED' ? 'exception' : undefined}
                />
                <Tag color={
                  taskPoll.data.status === 'SUCCESS' ? 'success' :
                  taskPoll.data.status === 'FAILED' ? 'error' : 'processing'
                }>{taskPoll.data.status}</Tag>
                {taskPoll.data.status === 'FAILED' && (
                  <Button size="small" icon={<ReloadOutlined />}
                    onClick={() => retryTask.mutate(taskPoll.data.id)} loading={retryTask.isPending}>
                    重试
                  </Button>
                )}
                {taskPoll.data.status !== 'RUNNING' && taskPoll.data.status !== 'PENDING' && (
                  <Button size="small" onClick={() => setTrackingDocId(undefined)}>收起</Button>
                )}
              </Space>
              {statusLabel && (
                <Space>
                  <span>当前步骤：</span>
                  <Tag color={statusLabel.color}>{docStatus}</Tag>
                  <span>{statusLabel.text}</span>
                </Space>
              )}
              {taskPoll.data.errorMessage && (
                <div style={{ color: '#ff4d4f' }}>错误：{taskPoll.data.errorMessage}</div>
              )}
            </Space>
          </Card>
        );
      })()}

      <Card className="upload-panel">
        <Upload.Dragger
          multiple
          showUploadList={false}
          disabled={uploading}
          fileList={uploadFiles}
          beforeUpload={() => false}
          onChange={({ fileList }) => {
            setUploadFiles(fileList);
            if (!uploading) {
              setUploadProgress(null);
            }
          }}
        >
          <InboxOutlined className="upload-icon" />
          <p>拖拽或点击选择多个文件</p>
          <span>文件数量不限，前端将按每批 20 个依次上传</span>
        </Upload.Dragger>
        {uploadFiles.length > 0 && (
          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message={`已选择 ${uploadFiles.length} 个文件`}
            description="上传时将按每批 20 个文件依次提交，文件处理状态会自动刷新。"
          />
        )}
        <Space style={{ marginTop: 16 }}>
          <Button
            type="primary"
            loading={uploading}
            disabled={uploadFiles.length === 0}
            onClick={() => void upload()}
          >
            上传 {uploadFiles.length > 0 ? `${uploadFiles.length} 个文件` : ''}
          </Button>
          {uploadFiles.length > 0 && !uploading && (
            <Button onClick={() => setUploadFiles([])}>清空列表</Button>
          )}
        </Space>
        {uploadProgress !== null && (
          <div className="upload-progress">
            <span>总体上传进度</span>
            <Progress
              percent={uploadProgress}
              size="small"
              status={uploading ? 'active' : undefined}
            />
          </div>
        )}
      </Card>

      <div className="filter-bar" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Input.Search allowClear placeholder="按文件名筛选"
          onChange={(e) => setSearch(e.target.value)} style={{ width: 320 }} />
        {selectedRowKeys.length > 0 && (
          <Popconfirm
            title={`确认删除选中的 ${selectedRowKeys.length} 个文档？`}
            onConfirm={() => batchRemove.mutate(selectedRowKeys)}
          >
            <Button danger icon={<DeleteOutlined />} loading={batchRemove.isPending}>
              批量删除（{selectedRowKeys.length}）
            </Button>
          </Popconfirm>
        )}
      </div>

      <Table
        rowKey="id"
        loading={docs.isLoading}
        dataSource={filtered}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys.map(String)),
        }}
        columns={[
          { title: '文件名', dataIndex: 'fileName' },
          { title: '类型', dataIndex: 'fileType' },
          { title: '大小', dataIndex: 'fileSize', render: (v) => `${(v / 1024).toFixed(1)} KB` },
          {
            title: '处理状态',
            dataIndex: 'parseStatus',
            render: (v: string) => {
              const s = PARSE_STATUS_LABEL[v as DocumentParseStatus]
                     ?? { color: 'default' as const, text: v };
              return <Tag color={s.color}>{s.text}</Tag>;
            },
          },
          {
            title: '处理进度',
            width: 180,
            render: (_, document: KnowledgeDocument) => {
              const task = runningTaskByDocumentId.get(document.id);

              // 文档终态优先于任务查询缓存，避免最后一次轮询残留旧进度。
              if (document.parseStatus === 'READY') {
                return <Progress percent={100} size="small" />;
              }

              if (document.parseStatus === 'FAILED') {
                return (
                  <Progress
                    percent={0}
                    size="small"
                    status="exception"
                  />
                );
              }

              if (task) {
                return (
                  <Progress
                    percent={task.progress}
                    size="small"
                    status="active"
                  />
                );
              }

              return <Progress percent={0} size="small" />;
            },
          },
          { title: '更新时间', dataIndex: 'updatedAt',
            render: (v) => new Date(v).toLocaleString() },
          {
            title: '操作',
            render: (_, r: KnowledgeDocument) => (
              <Space>
                {!completedIds.has(r.id) && (
                  <Button size="small" icon={<ReloadOutlined />}
                    loading={trackingDocId === r.id && taskPoll.isLoading}
                    onClick={() => setTrackingDocId(trackingDocId === r.id ? undefined : r.id)}>
                    {trackingDocId === r.id ? '收起进度' : '查看进度'}
                  </Button>
                )}
                <Button size="small" icon={<EyeOutlined />} onClick={() => setDoc(r)}>
                  查看分块
                </Button>
                <Popconfirm title="确认删除？" onConfirm={() => remove.mutate(r.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Drawer width={720} title={doc?.fileName} open={Boolean(doc)} onClose={() => setDoc(null)}>
        <Table<DocumentChunk> rowKey="id" loading={chunks.isLoading}
          dataSource={chunks.data} pagination={{ pageSize: 8 }}
          columns={[
            { title: '#', dataIndex: 'chunkIndex', width: 60 },
            { title: '内容', dataIndex: 'content',
              render: (v) => <div className="chunk-content">{v}</div> },
            { title: 'Token', dataIndex: 'tokenCount', width: 80 },
          ]}
        />
      </Drawer>
    </>
  );
}
