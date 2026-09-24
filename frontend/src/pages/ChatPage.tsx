import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Select, Spin, Tag, Typography } from 'antd';
import {
  ArrowUpOutlined,
  BookOutlined,
  CheckCircleOutlined,
  BulbOutlined,
  RobotOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import { chatApi, streamChat } from '../api/modules';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import type { ChatMessage } from '../types/api';

interface LiveMessage {
  role: 'USER' | 'ASSISTANT';
  content: string;
  citations?: unknown[];
  status?: 'pending' | 'error';
}

interface ChatContext {
  conversationId?: string;
}

const PRESETS = [
  { icon: <BookOutlined />, title: '内容总结', desc: '提炼 3-5 条关键信息与行动点', prompt: '请帮我总结以下内容，并列出3-5条要点：' },
  { icon: <CheckCircleOutlined />, title: '任务拆解', desc: '把目标拆成可执行步骤与优先级', prompt: '请把下面需求拆解为步骤，并给出优先级和里程碑：' },
  { icon: <BulbOutlined />, title: '灵感扩展', desc: '给出多个方案并比较优缺点', prompt: '围绕以下主题给出5-8个方案，并注明优缺点：' },
];

export function ChatPage() {
  const qc = useQueryClient(),
    { message } = App.useApp();
  const { conversationId } = useOutletContext<ChatContext>();
  const [, setSearchParams] = useSearchParams();

  const [question, setQuestion] = useState(''),
    [knowledgeBaseId, setKnowledgeBaseId] = useState<string>(),
    [live, setLive] = useState<LiveMessage[]>([]),
    [streaming, setStreaming] = useState(false);
  const abort = useRef<AbortController>();
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const kbs = useQuery({
    queryKey: ['chat', 'knowledge-bases'],
    queryFn: chatApi.availableKnowledgeBases,
  });

  const messages = useQuery({
    queryKey: ['messages', conversationId],
    queryFn: () => chatApi.messages(conversationId!),
    enabled: Boolean(conversationId),
  });

  useEffect(() => {
    setLive(
      (messages.data ?? []).map((m: ChatMessage) => ({
        role: m.role === 'USER' ? 'USER' : 'ASSISTANT',
        content: m.content,
      })),
    );
  }, [messages.data]);

  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [live]);

  const doSend = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;
      setQuestion('');
      setLive((v) => [
        ...v,
        { role: 'USER', content: text },
        { role: 'ASSISTANT', content: '', status: 'pending' },
      ]);
      setStreaming(true);
      abort.current = new AbortController();
      try {
        await streamChat(
          { question: text, conversationId, knowledgeBaseId },
          (event, data) => {
            const obj = typeof data === 'object' && data ? (data as Record<string, unknown>) : {};
            if (event === 'delta' || obj.type === 'delta') {
              const delta = String(obj.content ?? obj.delta ?? '');
              setLive((v) =>
                v.map((m, i) =>
                  i === v.length - 1
                    ? { ...m, content: m.content + delta, status: 'pending' }
                    : m,
                ),
              );
            }
            if (event === 'final' || obj.type === 'final') {
              const answer = String(obj.answer ?? obj.content ?? '');
              const nextId =
                typeof obj.conversationId === 'string'
                  ? obj.conversationId
                  : typeof obj.conversationId === 'number'
                    ? String(obj.conversationId)
                    : undefined;
              if (nextId) setSearchParams({ conversationId: nextId });
              setLive((v) =>
                v.map((m, i) =>
                  i === v.length - 1
                    ? {
                        ...m,
                        content: answer || m.content,
                        citations: Array.isArray(obj.citations) ? obj.citations : undefined,
                        status: undefined,
                      }
                    : m,
                ),
              );
            }
            if (event === 'error') throw new Error(String(obj.message ?? '生成失败'));
          },
          abort.current.signal,
        );
        void qc.invalidateQueries({ queryKey: ['conversations'] });
      } catch (e) {
        if (!abort.current.signal.aborted) message.error(e instanceof Error ? e.message : '生成失败');
        setLive((v) =>
          v.map((m, i) =>
            i === v.length - 1 && m.role === 'ASSISTANT' && !m.content
              ? { ...m, status: 'error' }
              : m,
          ),
        );
        abort.current.abort();
      } finally {
        setStreaming(false);
      }
    },
    [streaming, conversationId, knowledgeBaseId, setSearchParams, qc, message],
  );

  const handleSend = () => doSend(question);
  const handlePreset = (prompt: string) => doSend(prompt);
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const hasMessages = live.length > 0;

  const adjustTextarea = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  useLayoutEffect(() => { adjustTextarea(); }, [question]);

  const renderComposer = () => (
    <div className="chat-composer">
      <textarea
        ref={inputRef}
        className="composer-textarea"
        rows={3}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入问题，Enter 发送，Shift + Enter 换行"
      />
      <Button
        type="primary"
        shape="circle"
        size="small"
        icon={streaming ? <StopOutlined /> : <ArrowUpOutlined />}
        onClick={() => (streaming ? abort.current?.abort() : handleSend())}
        disabled={!question.trim() && !streaming}
        className="composer-send-btn"
      />
    </div>
  );

  return (
    <div className="chat-main-area">
      {hasMessages && (
        <div className="chat-toolbar">
          <div className="chat-toolbar-inner">
            <Select
              allowClear
              placeholder="选择知识库"
              value={knowledgeBaseId}
              onChange={setKnowledgeBaseId}
              options={kbs.data?.map((k) => ({ value: k.id, label: k.name }))}
              style={{ width: 260 }}
              variant="borderless"
            />
            <Tag color="blue">RAG</Tag>
          </div>
        </div>
      )}

      <div ref={messagesRef} className={`chat-messages ${!hasMessages ? 'chat-messages--welcome' : ''}`}>
        {!hasMessages ? (
          <div className="chat-welcome">
            <div className="welcome-top">
              <div className="welcome-icon">
                <RobotOutlined />
              </div>
              <Typography.Title level={2} className="welcome-title">
                我是 Nexus RAG
              </Typography.Title>
              <Typography.Text className="welcome-desc">
                基于知识库的智能问答助手
              </Typography.Text>
            </div>

            <div className="welcome-presets">
              {PRESETS.map((p) => (
                <div key={p.title} className="preset-card" onClick={() => handlePreset(p.prompt)}>
                  <div className="preset-icon">{p.icon}</div>
                  <div className="preset-body">
                    <Typography.Text strong className="preset-title">{p.title}</Typography.Text>
                    <Typography.Text type="secondary" className="preset-desc">{p.desc}</Typography.Text>
                  </div>
                </div>
              ))}
            </div>

            <div className="welcome-input">
              {renderComposer()}
            </div>
          </div>
        ) : (
          <div className="chat-messages-inner">
            {live.map((m, i) => (
              <div key={i} className={`message ${m.role.toLowerCase()}`}>
                {m.role === 'USER' && <div className="message-role">你</div>}
                <div className="message-body">
                  {m.content ? (
                    <MarkdownRenderer content={m.content} />
                  ) : m.status === 'error' ? (
                    <Typography.Text type="danger">生成失败，请重试</Typography.Text>
                  ) : (
                    <Spin size="small" />
                  )}
                  {m.citations && <div className="citations">引用来源 {m.citations.length} 条</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {hasMessages && (
        <div className="chat-composer-wrapper">
          <div className="chat-composer-inner">
            {renderComposer()}
          </div>
        </div>
      )}
    </div>
  );
}
