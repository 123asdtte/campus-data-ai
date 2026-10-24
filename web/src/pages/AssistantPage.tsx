import { useState } from 'react';
import { Alert, Button, Tag } from 'antd';
import { Input } from 'antd';
import { RobotOutlined, SendOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { askAssistant, type AssistantReply } from '../api/assistant';
import { PageHeader } from '../components/ui';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  reply?: AssistantReply;
  failed?: boolean;
  retry?: string;
}

interface AuditLog {
  time: string;
  question: string;
  intent: string;
}

const SUGGESTIONS = [
  '人工智能学院有多少学生？',
  '全校休学和退学各有多少人？',
  '数据质量怎么样？',
  '帮我找 SK-2026-000004',
  '还有哪些异动没核对？',
];

const INTENT_LABELS: Record<string, string> = {
  help: '能力说明',
  quality: '数据质量 · 聚合口径',
  report: '报表引导',
  changes: '学籍异动 · 聚合口径',
  pending: '异动待办',
  change_count: '异动统计',
  change_found: '异动检索 · 已定位',
  change_not_found: '异动检索 · 无结果/越界',
  change_query_needs_identifier: '异动检索 · 需要异动编号',
  count: '人数统计',
  profile: '本人学籍信息',
  student_found: '学生检索 · 已定位',
  student_ambiguous: '学生检索 · 同名候选',
  student_not_found: '学生检索 · 无结果/越界',
  student_query_needs_identifier: '学生检索 · 需要 UID/姓名',
  refused: '超出可回答范围',
  out_of_scope: '超出数据范围',
  unknown: '未识别意图',
};

const LOG_KEY = 'campus.demo.aiLogs.v1';

function loadLogs(): AuditLog[] {
  try {
    const raw = window.localStorage.getItem(LOG_KEY);
    return raw ? (JSON.parse(raw) as AuditLog[]) : [];
  } catch {
    return [];
  }
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: '问数由服务端按你的登录身份限定范围后回答，可以问学院人数、休学/退学、数据质量或异动；也可以按 UID/脱敏姓名检索学生并打开档案。当前不调用外部模型，数据只在本机。',
    },
  ]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const [logs, setLogs] = useState<AuditLog[]>(loadLogs);

  const lastSuggestions = [...messages].reverse().find((m) => m.reply)?.reply?.suggestions;
  const suggestions = lastSuggestions?.length ? lastSuggestions : SUGGESTIONS;

  const send = async (value: string) => {
    const question = value.trim();
    if (!question || pending) return;
    setMessages((current) => [
      ...current,
      { id: `u-${Date.now()}`, role: 'user', text: question },
    ]);
    setInput('');
    setPending(true);
    try {
      const reply = await askAssistant(question, '/assistant');
      setMessages((current) => [
        ...current,
        { id: `a-${Date.now()}`, role: 'assistant', text: reply.answer, reply },
      ]);
      const next = [
        {
          time: new Date().toLocaleString('zh-CN', { hour12: false }),
          question,
          intent: INTENT_LABELS[reply.intent] ?? reply.intent,
        },
        ...logs,
      ].slice(0, 8);
      setLogs(next);
      window.localStorage.setItem(LOG_KEY, JSON.stringify(next));
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : '问数失败';
      setMessages((current) => [
        ...current,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          text: `${message} 服务端没有返回结果，本回答不含推测数据。`,
          failed: true,
          retry: question,
        },
      ]);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="wb">
      <PageHeader
        title="AI 问数"
        description="服务端按登录身份限定数据范围后回答；学生账号在“我的课表”或悬浮助手里使用只读课表问答。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">SERVER RULES</span>
            <span className="wb-badge is-demo">演示数据 · 不出本机</span>
          </div>
        }
      />

      <div className="ai-layout">
        <section className="wb-panel ai-chat">
          <header className="wb-panel-head">
            <h2>全局问数</h2>
            <span><RobotOutlined /> 服务端规则 · Dify 接入位</span>
          </header>
          <div className="ai-messages">
            {messages.map((message) => (
              <div className={`ai-message is-${message.role}`} key={message.id}>
                <div className={`ai-bubble${message.failed ? ' is-error' : ''}`}>
                  <p>{message.text}</p>
                  {message.reply ? (
                    <small>
                      {INTENT_LABELS[message.reply.intent] ?? message.reply.intent}
                      {message.reply.scope?.label ? ` · ${message.reply.scope.label}` : ''}
                      {message.reply.as_of ? ` · 截至 ${message.reply.as_of}` : ''}
                    </small>
                  ) : null}
                  {message.reply?.note ? <small className="ai-note">{message.reply.note}</small> : null}
                  {message.reply?.students?.length ? (
                    <div className="ai-students">
                      {message.reply.students.map((student) => (
                        <Link className="ai-student" key={student.uid} to={student.profile_to}>
                          <span className="ai-student-id">{student.uid}</span>
                          <b>{student.name}</b>
                          <small>{student.class_short || student.class_name} · {student.status} · {student.college}</small>
                        </Link>
                      ))}
                    </div>
                  ) : null}
                  {message.reply?.changes?.length ? (
                    <div className="ai-changes">
                      {message.reply.changes.map((change) => (
                        <Link className="ai-change" key={change.change_no} to={change.change_to}>
                          <span className="ai-change-no">{change.change_no}</span>
                          <b>{change.type} · {change.name}</b>
                          <small>{change.class_short} · {change.date} · {change.status} · {change.platform_status}</small>
                        </Link>
                      ))}
                    </div>
                  ) : null}
                  {message.reply?.action ? (
                    <Link className="ai-action" to={message.reply.action.to}>{message.reply.action.label} →</Link>
                  ) : null}
                  {message.failed && message.retry ? (
                    <Button size="small" onClick={() => void send(message.retry as string)} disabled={pending}>
                      重试
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
            {pending ? <div className="ai-message is-assistant"><div className="ai-bubble ai-thinking">正在按服务端规则查询演示数据…</div></div> : null}
          </div>
          <div className="ai-suggestions">
            {suggestions.map((item) => (
              <button type="button" key={item} onClick={() => void send(item)} disabled={pending}>{item}</button>
            ))}
          </div>
          <div className="ai-input">
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={() => void send(input)}
              aria-label="输入问题"
              placeholder="问：人工智能学院有多少学生 / 全校休学和退学各有多少人"
              disabled={pending}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={() => void send(input)} loading={pending}>
              发送
            </Button>
          </div>
        </section>

        <aside className="ai-side">
          <section className="wb-panel">
            <header className="wb-panel-head"><h2>当前边界</h2><span>演示版</span></header>
            <ul className="wb-uid-list">
              <li>身份、权限与数据范围都在服务端判定，前端不传 UID 或角色。</li>
              <li>只返回聚合与脱敏结果，不返回身份证、电话、原始学号。</li>
              <li>学生检索按 UID/脱敏姓名，唯一命中才给档案；同名只给候选，范围外不打开。</li>
              <li>异动卡片只带编号/类型/日期/核对状态，点开台账定位；AI 不执行核对或写入。</li>
              <li>管理员/学工处为全校范围，辅导员只得到本班范围；与页面数据口径一致。</li>
              <li>不调用外部模型；接入 Dify 后只替换意图解析，工具仍走同一批服务端接口。</li>
              <li>提问内容留在本机，服务端只记录意图，正式版写服务端审计。</li>
            </ul>
          </section>

          <section className="wb-panel">
            <header className="wb-panel-head"><h2>问数记录</h2><span>本机 · 最近 8 条</span></header>
            {logs.length ? (
              <div className="rp-log-list">
                {logs.map((log, index) => (
                  <div className="rp-log" key={`${log.time}-${index}`}>
                    <span>{log.time}</span>
                    <b>{log.question}</b>
                    <small>{log.intent}</small>
                  </div>
                ))}
              </div>
            ) : (
              <p className="wb-note">还没有提问记录；点一个建议问题试试。</p>
            )}
          </section>

          <section className="wb-panel">
            <header className="wb-panel-head"><h2>Dify 接入位</h2><span>下一步</span></header>
            <Alert
              type="info"
              showIcon={false}
              message="旁路 AI 层，不直连业务库"
              description="模型只负责把问题转成受约束的意图与参数，统计与导出仍调用平台已有接口；真实数据阶段使用本地/校内模型，并单独确认存储、访问、留存与调用链。"
            />
            <Tag color="blue">P1 · 本地/校内模型</Tag>
          </section>
        </aside>
      </div>

      <p className="wb-footnote">演示数据，非真实人员信息 · AI 问数为服务端规则模式，不调用外部模型</p>
    </div>
  );
}
