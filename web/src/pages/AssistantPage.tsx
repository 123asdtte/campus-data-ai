import { useMemo, useState } from 'react';
import { Button, Input, Tag } from 'antd';
import { RobotOutlined, SendOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/ui';
import { fmt } from '../demo/format';
import type { DemoData } from '../demo/types';
import { useDemoData } from '../demo/useDemoData';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  meta?: string;
  action?: { label: string; to: string };
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
  '生成退学名单',
  '最近的学籍异动情况',
];

const COLLEGE_ALIASES: Record<string, string> = {
  计算机: '人工智能学院',
  人工智能: '人工智能学院',
  护理: '康养护理学院',
  康养: '康养护理学院',
  汽车: '汽车工程学院',
  财经: '财经商贸学院',
  会计: '财经商贸学院',
  轨道: '轨道交通学院',
  智能装备: '智能装备学院',
  机电: '智能装备学院',
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

function findCollege(question: string, data: DemoData): string | null {
  for (const item of data.metrics.college_counts) {
    if (question.includes(item.name)) return item.name;
  }
  for (const [alias, name] of Object.entries(COLLEGE_ALIASES)) {
    if (question.includes(alias)) return name;
  }
  return null;
}

function findStatuses(question: string, data: DemoData): string[] {
  const statuses = data.metrics.status_counts.map((item) => item.name);
  const found = statuses.filter((status) => question.includes(status));
  if (question.includes('在校') && !found.includes('在籍')) found.push('在籍');
  return found;
}

function buildAnswer(question: string, data: DemoData): ChatMessage {
  const q = question.trim();
  const college = findCollege(q, data);
  const statuses = findStatuses(q, data);
  const scopeLabel = college ?? '全校';
  const base = college ? data.students.filter((student) => student.college === college) : data.students;

  const isHelp = ['帮助', '能做什么', '怎么用', '你好'].some((word) => q.includes(word));
  const isQuality = ['数据质量', '缺', '异常', '同名', '身份证', '数据标记'].some((word) => q.includes(word));
  const isReport = ['名单', '报表', '导出', '表格'].some((word) => q.includes(word));
  const isChange = ['异动', '休学', '退学', '转专业', '变化'].some((word) => q.includes(word));
  const isCount = ['多少', '人数', '几个', '几名', '统计'].some((word) => q.includes(word));

  if (isHelp) {
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      text: '我可以按学院/学籍状态统计人数、解释异动分布、检查数据质量，或引导你到报表中心生成名单。当前是本地规则模式，只返回聚合与脱敏信息，不返回身份证、电话或原始学号。',
      meta: '能力说明 · 本地规则',
      action: { label: '打开报表中心', to: '/reports' },
    };
  }

  if (isQuality) {
    const quality = data.metrics.data_quality;
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      text: `当前演示数据有 ${fmt(data.metrics.total_students)} 名学生。需重点核对：重复学号 ${quality.duplicate_rows?.count ?? 0} 行、同班同名 ${quality.same_name_groups?.count ?? 0} 组、身份证校验异常 ${quality.id_invalid?.count ?? 0} 条、班级名称未匹配 ${quality.class_not_found?.count ?? 0} 人、转专业已批但花名册未更新 ${quality.transfer_conflicts?.count ?? 0} 条。另有同名同姓 ${fmt(quality.same_name_all?.count ?? 0)} 组，仅作提示。`,
      meta: '数据质量 · 聚合口径',
      action: { label: '查看数据工作台', to: '/workbench' },
    };
  }

  if (isReport) {
    const template = q.includes('退学')
      ? '退学名单'
      : q.includes('异动')
        ? '学籍异动名单'
        : q.includes('学平险')
          ? '学平险名单'
          : '班级花名册';
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      text: `可以到报表中心使用「${template}」模板：选择字段、筛选范围后导出。导出只包含 UID 和脱敏字段，并记录操作人/时间。`,
      meta: `报表引导 · ${template}`,
      action: { label: '打开报表中心', to: '/reports' },
    };
  }

  if (isChange && !isCount) {
    const top = data.metrics.change_type_counts.slice(0, 3).map((item) => `${item.name} ${item.count}`).join('、');
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      text: `演示数据共有 ${fmt(data.metrics.change_total)} 条学籍异动记录；主要类型：${top}。异动需要教务确认后才联动学生状态。`,
      meta: '学籍异动 · 聚合口径',
      action: { label: '打开学籍异动', to: '/changes' },
    };
  }

  if (isCount || isChange) {
    if (statuses.length > 1) {
      const parts = statuses.map((status) => `${status} ${fmt(base.filter((student) => student.status === status).length)} 人`);
      return {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: `${scopeLabel}：${parts.join('，')}。统计范围为${college ? '本学院' : '全校'}演示数据，未含原始学号与联系方式。`,
        meta: `按状态统计 · ${scopeLabel}`,
      };
    }
    if (statuses.length === 1) {
      const count = base.filter((student) => student.status === statuses[0]).length;
      return {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: `${scopeLabel}学籍状态为「${statuses[0]}」的学生共 ${fmt(count)} 人。统计范围：${college ? '本学院' : '全校'}演示数据。`,
        meta: `按状态统计 · ${scopeLabel}`,
      };
    }
    return {
      id: `a-${Date.now()}`,
      role: 'assistant',
      text: `${scopeLabel}共有 ${fmt(base.length)} 名学生，其中在籍 ${fmt(base.filter((student) => student.status === '在籍').length)} 人。统计口径为去重后演示数据。`,
      meta: `学生人数 · ${scopeLabel}`,
    };
  }

  return {
    id: `a-${Date.now()}`,
    role: 'assistant',
    text: '我暂时只理解人数统计、学籍状态、数据质量、学籍异动和报表引导。你可以试试：“人工智能学院有多少学生”“全校休学和退学各有多少人”“数据质量怎么样”。',
    meta: '本地规则 · 未识别意图',
    action: { label: '看能力说明', to: '/workbench' },
  };
}

export default function AssistantPage() {
  const { data } = useDemoData();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: '你好，我是本地规则问数助手。可以问学院人数、休学/退学、数据质量或异动；当前不调用外部模型，数据只在本机。',
      meta: '本地模式 · 演示数据',
    },
  ]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const [logs, setLogs] = useState<AuditLog[]>(loadLogs);

  const suggestions = useMemo(() => SUGGESTIONS, []);

  const send = (text: string) => {
    if (!data || !text.trim() || thinking) return;
    const question = text.trim();
    const userMessage: ChatMessage = { id: `u-${Date.now()}`, role: 'user', text: question };
    setMessages((current) => [...current, userMessage]);
    setInput('');
    setThinking(true);
    window.setTimeout(() => {
      const answer = buildAnswer(question, data);
      setMessages((current) => [...current, answer]);
      setThinking(false);
      const next = [
        { time: new Date().toLocaleString('zh-CN', { hour12: false }), question, intent: answer.meta ?? '未知' },
        ...logs,
      ].slice(0, 8);
      setLogs(next);
      window.localStorage.setItem(LOG_KEY, JSON.stringify(next));
    }, 320);
  };

  return (
    <div className="wb">
      <PageHeader
        title="AI 问数"
        description="管理员演示视角：全校聚合问数；学生账号在“我的课表”里使用只读课表助手，不进入这个全局问数页。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">LOCAL RULE</span>
            <span className="wb-badge is-demo">演示数据 · 不出本机</span>
          </div>
        }
      />

      <div className="ai-layout">
        <section className="wb-panel ai-chat">
          <header className="wb-panel-head">
            <h2>本地问数</h2>
            <span><RobotOutlined /> 规则 planner · Dify 接入位</span>
          </header>
          <div className="ai-messages">
            {messages.map((message) => (
              <div className={`ai-message is-${message.role}`} key={message.id}>
                <div className="ai-bubble">
                  <p>{message.text}</p>
                  {message.meta ? <small>{message.meta}</small> : null}
                  {message.action ? <Link className="ai-action" to={message.action.to}>{message.action.label} →</Link> : null}
                </div>
              </div>
            ))}
            {thinking ? <div className="ai-message is-assistant"><div className="ai-bubble ai-thinking">正在按本地规则查演示数据…</div></div> : null}
          </div>
          <div className="ai-suggestions">
            {suggestions.map((item) => (
              <button type="button" key={item} onClick={() => send(item)}>{item}</button>
            ))}
          </div>
          <div className="ai-input">
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={() => send(input)}
              aria-label="输入问题"
              placeholder="问：人工智能学院有多少学生 / 全校休学和退学各有多少人"
              disabled={thinking}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={() => send(input)} loading={thinking}>
              发送
            </Button>
          </div>
        </section>

        <aside className="ai-side">
          <section className="wb-panel">
            <header className="wb-panel-head"><h2>当前边界</h2><span>演示版</span></header>
            <ul className="wb-uid-list">
              <li>只做聚合与脱敏结果，不返回身份证、电话、原始学号。</li>
              <li>管理员演示为全校范围；正式版按登录角色限制学院/班级。</li>
              <li>不调用外部模型；Dify/本地模型接入后替换 planner，工具仍走平台 API。</li>
              <li>每次提问记录在本机浏览器；正式版写服务端审计。</li>
            </ul>
            <div className="wb-source">当前数据：{fmt(data?.metrics.total_students ?? 0)} 名虚构学生 · 6 个学院 · 演示库</div>
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
            <p className="wb-note">
              Dify 作为旁路 AI 层，不直连业务库；只调用平台的报表/聚合/异常解释 API。
              真实数据阶段使用本地/校内模型，并单独确认存储、访问、留存与模型调用链。
            </p>
            <Tag color="blue">P1 · 本地/校内模型</Tag>
          </section>
        </aside>
      </div>

      <p className="wb-footnote">演示数据，非真实人员信息 · AI 问数为本地规则模式，不调用外部模型</p>
    </div>
  );
}
