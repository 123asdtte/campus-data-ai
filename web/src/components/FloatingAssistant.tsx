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
  '/counselor': ['还有哪些异动没核对？', '最近的学籍异动情况', '异动台账里休学和退学各有多少条？'],
  '/workbench': ['人工智能学院有多少学生？', '数据质量怎么样？', '有哪些报表可以下载？', '全校学生总数是多少？'],
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

const PROFILE_SUGGESTIONS = [
  '他的异动记录有哪些？',
  '他的学籍状态是什么？',
  '打开异动台账',
];

const CHANGE_SUGGESTIONS = [
  '这条异动核对了吗？',
  '最近的学籍异动情况',
  '打开学籍异动',
];

// 服务端只会下发受控的内部路由；前端仍再校验一次，避免把任意 URL 交给 navigate。
function safeInternalPath(to?: string): string | null {
  return to && to.startsWith('/') && !to.startsWith('//') ? to : null;
}

// 回答的来源口径：数据范围 + 这批演示数据的截止时间。悬浮面板原先只显示范围，
// 学生问「明天有什么课」时看不出课表数据是哪一刻取的；两段拼进同一行，不新增样式。
function formatAsOf(value: string): string {
  // 面板宽 392px（窄屏下 width:auto），`2026-10-24T21:36:20+08:00` 会把这枚小药丸挤成两行。
  // 精确到分足够回答「这数据新不新」，秒和时区在这种场景没人读。
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(value);
  return match ? `${match[1]} ${match[2]}` : value;
}

function replyMeta(reply?: AssistantReply): string {
  return [
    reply?.scope?.label ? `数据范围 · ${reply.scope.label}` : '',
    reply?.as_of ? `截至 ${formatAsOf(reply.as_of)}` : '',
  ].filter(Boolean).join(' · ');
}

export default function FloatingAssistant() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const { session } = useSession();
  const isStudent = session?.roles.includes('student_portal') ?? false;
  const searchParams = new URLSearchParams(search);
  const contextStudent = searchParams.get('student') ?? undefined;
  const contextChange = searchParams.get('change') ?? undefined;
  const isChangeContext = Boolean(contextChange);
  const isProfileContext = Boolean(contextStudent);
  // AI 问数页本身就是一个完整对话界面，再挂悬浮入口只会重复。
  const embedded = pathname === '/assistant';
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesBox = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // 用户停在底部时，新回答（尤其带卡片的异动/学生结果）要跟随滚到底；
  // 用户主动向上回看时不要抢滚动。发送新问题视为明确要跟进最新回答。
  useEffect(() => {
    const el = messagesBox.current;
    if (!el) return;
    if (stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  const onMessagesScroll = () => {
    const el = messagesBox.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  const contextLabel = isChangeContext
    ? '异动记录'
    : isProfileContext
      ? '学生档案'
      : PAGE_TITLES[pathname] ?? '数据管理';
  const staticSuggestions = isStudent
    ? STUDENT_SUGGESTIONS
    : isChangeContext
      ? CHANGE_SUGGESTIONS
      : isProfileContext
        ? PROFILE_SUGGESTIONS
        : PAGE_SUGGESTIONS[pathname] ?? STAFF_SUGGESTIONS;
  // 服务端会针对这次回答给出下一步问法（与完整问数页同一份数据）。悬浮面板原先一直丢掉它，
  // 于是「下周有哪些课」这种追问要用户自己再打一遍；现在优先用服务端的，静态列表只做兜底。
  const lastSuggestions = [...messages].reverse().find((message) => message.reply)?.reply?.suggestions;
  const suggestions = lastSuggestions?.length ? lastSuggestions : staticSuggestions;
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
      if (event.key !== 'Escape') return;
      // 抽屉/弹窗盖在面板之上时，Esc 应该只关最上面那层；否则用户关掉学生详情
      // 却发现背后的对话也被一起收掉了，正在问的问题就没了。
      if (document.querySelector('.ant-drawer-open, .ant-modal-wrap')) return;
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const ask = async (value: string) => {
    const question = value.trim();
    if (!question || pending) return;
    stickToBottom.current = true;
    setMessages((current) => [
      ...current,
      { id: `u-${Date.now()}`, role: 'user', text: question },
    ]);
    setInput('');
    setPending(true);
    try {
      const reply = await askAssistant(question, pathname, {
        student_uid: contextStudent,
        change_no: contextChange,
      });
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
    // 带上课程名：课表页要据此判断这堂课在当前周次是否真的可见，不能空定位
    const detail = { weekday: course.weekday, period: course.period, course: course.course };
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

          <div className="fa-messages" ref={messagesBox} onScroll={onMessagesScroll} aria-live="polite">
            {messages.map((message) => {
              const meta = replyMeta(message.reply);
              return (
              <div className={`fa-message is-${message.role}`} key={message.id}>
                <div className={`fa-bubble${message.error ? ' is-error' : ''}`}>
                  <p>{message.text}</p>
                  {meta ? <span className="fa-scope">{meta}</span> : null}
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
                  {message.reply?.students?.length ? (
                    <div className="fa-students">
                      {message.reply.students.map((student) => {
                        const target = safeInternalPath(student.profile_to);
                        return (
                          <button
                            type="button"
                            className="fa-student"
                            key={student.uid}
                            aria-label={`查看学生 ${student.uid}`}
                            disabled={!target}
                            onClick={() => {
                              if (!target) return;
                              setOpen(false);
                              navigate(target);
                            }}
                          >
                            <span className="fa-student-id">{student.uid}</span>
                            <b>{student.name}</b>
                            <small>{student.class_short || student.class_name} · {student.status} · {student.college}</small>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  {message.reply?.changes?.length ? (
                    <div className="fa-changes">
                      {message.reply.changes.map((change) => {
                        const target = safeInternalPath(change.change_to);
                        return (
                          <button
                            type="button"
                            className="fa-change"
                            key={change.change_no}
                            aria-label={`查看异动 ${change.change_no}`}
                            disabled={!target}
                            onClick={() => {
                              if (!target) return;
                              setOpen(false);
                              navigate(target);
                            }}
                          >
                            <span className="fa-change-no">{change.change_no}</span>
                            <b>{change.type} · {change.name}</b>
                            <small>{change.class_short} · {change.date} · {change.status} · {change.platform_status}</small>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  {message.reply?.action ? (
                    <button
                      type="button"
                      className="fa-action"
                      onClick={() => {
                        const target = safeInternalPath(message.reply!.action!.to);
                        if (!target) return;
                        navigate(target);
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
              );
            })}
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
