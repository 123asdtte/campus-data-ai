import { useEffect, useRef, useState } from 'react';
import { Button, Input } from 'antd';
import { CloseOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { askAssistant, type AssistantCourse, type AssistantReply } from '../api/assistant';
import { PAGE_TITLES } from '../pageTitles';
import { useSession } from '../session/SessionContext';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  reply?: AssistantReply;
  error?: boolean;
  retry?: string;
}

// 只列服务端确实能答的问法（意图已在 demo-api 单测里锁定），按当前页面换掉最贴身的三条。
const PAGE_SUGGESTIONS: Record<string, string[]> = {
  '/changes': ['还有哪些异动没核对？', '最近的学籍异动情况', '异动台账里休学和退学各有多少条？'],
  '/reports': ['有哪些报表可以下载？', '导出全校学生名单', '全校学生总数是多少？'],
  '/pipeline': ['数据质量怎么样？', '最近的学籍异动情况', '全校学生总数是多少？'],
  '/import': ['数据质量怎么样？', '有哪些报表可以下载？'],
  '/students': ['全校休学和退学各有多少人？', '人工智能学院有多少学生？', '数据质量怎么样？'],
};

const STUDENT_SUGGESTIONS = [
  '明天下午有什么课？',
  '今天还剩几节课？',
  '这周五第一节在哪？',
  '下周有哪些课？',
  '我的学籍状态是什么？',
];

const STAFF_SUGGESTIONS = [
  '人工智能学院有多少学生？',
  '全校休学和退学各有多少人？',
  '数据质量怎么样？',
  '最近的学籍异动情况',
];

export default function FloatingAssistant() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { session } = useSession();
  const isStudent = session?.roles.includes('student_portal') ?? false;
  // AI 问数页本身就是一个完整对话界面，再挂悬浮入口只会重复。
  const embedded = pathname === '/assistant';
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesBox = useRef<HTMLDivElement>(null);

  // 面板最高 620px，多轮问答后最新回答会落在可视区外；用户正在回看历史时不要抢滚动。
  useEffect(() => {
    const el = messagesBox.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  const contextLabel = PAGE_TITLES[pathname] ?? '数据管理';
  const suggestions = isStudent ? STUDENT_SUGGESTIONS : PAGE_SUGGESTIONS[pathname] ?? STAFF_SUGGESTIONS;
  const welcome = isStudent
    ? '我是你的课表助手，只读取你自己的班级课表和本人学籍档案。可以问：明天下午有什么课、今天还剩几节课、这周五第一节在哪、我的学籍状态是什么。'
    : '我是数据助手，按当前账号的数据范围统计人数、学籍状态、异动分布和数据质量；不返回身份证、电话或原始学号。';

  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{ id: 'welcome', role: 'assistant', text: welcome }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isStudent]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const ask = async (value: string) => {
    const question = value.trim();
    if (!question || pending) return;
    setMessages((current) => [
      ...current,
      { id: `u-${Date.now()}`, role: 'user', text: question },
    ]);
    setInput('');
    setPending(true);
    try {
      const reply = await askAssistant(question, pathname);
      setMessages((current) => [
        ...current,
        { id: `a-${Date.now()}`, role: 'assistant', text: reply.answer, reply },
      ]);
    } catch (reason) {
      setMessages((current) => [
        ...current,
        {
          id: `e-${Date.now()}`,
          role: 'assistant',
          text: reason instanceof Error ? reason.message : '查询失败，请重试。',
          error: true,
          retry: question,
        },
      ]);
    } finally {
      setPending(false);
    }
  };

  const focusCourse = (course: AssistantCourse) => {
    const detail = { weekday: course.weekday, period: course.period };
    setOpen(false);
    if (pathname === '/my-schedule') {
      window.dispatchEvent(new CustomEvent('campus:focus-course', { detail }));
      return;
    }
    navigate('/my-schedule', { state: { focusCourse: detail } });
  };

  if (embedded) return null;

  return (
    <>
      <button
        type="button"
        className={`fa-trigger${open ? ' is-open' : ''}`}
        aria-label={open ? '收起 AI 助手' : '打开 AI 助手'}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <RobotOutlined />
        <span>AI</span>
      </button>

      {open ? (
        <section className="fa-panel" role="dialog" aria-label="AI 助手">
          <header className="fa-head">
            <div className="fa-head-main">
              <span className="fa-orb"><RobotOutlined /></span>
              <div>
                <b>AI 助手</b>
                <small>当前页面 · {contextLabel}</small>
              </div>
            </div>
            <button type="button" className="fa-close" aria-label="收起 AI 助手" onClick={() => setOpen(false)}>
              <CloseOutlined />
            </button>
          </header>

          <div className="fa-messages" ref={messagesBox} aria-live="polite">
            {messages.map((message) => (
              <div className={`fa-message is-${message.role}`} key={message.id}>
                <div className={`fa-bubble${message.error ? ' is-error' : ''}`}>
                  <p>{message.text}</p>
                  {message.reply?.scope?.label ? (
                    <span className="fa-scope">数据范围 · {message.reply.scope.label}</span>
                  ) : null}
                  {message.reply?.courses.length ? (
                    <div className="fa-courses">
                      {message.reply.courses.map((course, index) => (
                        <button
                          type="button"
                          className="fa-course"
                          key={`${course.weekday}-${course.period}-${course.course}-${index}`}
                          onClick={() => focusCourse(course)}
                          title="在课表中定位"
                        >
                          <span className="fa-course-period">
                            {course.weekday} · {course.period}
                          </span>
                          <b>{course.course}</b>
                          <small>{course.teacher} · {course.room}</small>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {message.reply?.action ? (
                    <button
                      type="button"
                      className="fa-action"
                      onClick={() => {
                        navigate(message.reply!.action!.to);
                        setOpen(false);
                      }}
                    >
                      {message.reply.action.label} →
                    </button>
                  ) : null}
                  {message.reply?.note ? <small className="fa-note">{message.reply.note}</small> : null}
                  {message.retry ? (
                    <button type="button" className="fa-retry" onClick={() => ask(message.retry!)}>
                      重试
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
            {pending ? (
              <div className="fa-message is-assistant">
                <div className="fa-bubble fa-thinking">正在按你的身份查询…</div>
              </div>
            ) : null}
          </div>

          <div className="fa-suggestions">
            {suggestions.map((item) => (
              <button type="button" key={item} onClick={() => ask(item)} disabled={pending}>
                {item}
              </button>
            ))}
          </div>

          <div className="fa-input">
            <Input
              aria-label="向 AI 助手提问"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={() => ask(input)}
              placeholder={isStudent ? '问：今天还剩几节课？' : '问：某学院有多少学生？'}
              disabled={pending}
              autoFocus
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              aria-label="发送问题"
              onClick={() => ask(input)}
              loading={pending}
            />
          </div>
          <p className="fa-foot">服务端按登录身份校验数据范围 · 当前为演示数据</p>
        </section>
      ) : null}
    </>
  );
}
