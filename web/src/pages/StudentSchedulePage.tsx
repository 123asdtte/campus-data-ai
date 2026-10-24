import { useMemo, useState } from 'react';
import { Alert, Button, Empty, Input, Spin, Tag } from 'antd';
import { CalendarOutlined, SendOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/ui';
import { fmt } from '../demo/format';
import type { DemoStudent, ScheduleRow } from '../demo/types';
import { useDemoData } from '../demo/useDemoData';
import { useSession } from '../session/SessionContext';

const DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
}

function currentDayName(): string {
  const jsDay = new Date().getDay();
  return DAYS[(jsDay + 6) % 7];
}

function nextDayName(day: string): string {
  const index = DAYS.indexOf(day);
  return DAYS[(index + 1) % DAYS.length];
}

function weekMatches(weeks: string, currentWeek: number): boolean {
  const text = weeks || '';
  if (!text) return true;
  if (text.includes('单') && currentWeek % 2 === 0) return false;
  if (text.includes('双') && currentWeek % 2 === 1) return false;
  const numbers = [...text.matchAll(/\d+/g)].map((item) => Number(item[0]));
  if (!numbers.length) return true;
  const ranges = [...text.matchAll(/(\d+)\s*-\s*(\d+)/g)];
  if (ranges.length) {
    return ranges.some((range) => currentWeek >= Number(range[1]) && currentWeek <= Number(range[2]));
  }
  return numbers.includes(currentWeek);
}

function periodLabel(row: ScheduleRow): string {
  return row.period || '—';
}

function periodSlot(row: ScheduleRow): string {
  return row.period || '';
}

function courseLine(row: ScheduleRow): string {
  const room = row.room || (row.note ? row.note : '地点待定');
  return `${periodLabel(row)} ${row.course}（${row.teacher || '教师待定'}，${room}）`;
}

function buildScheduleAnswer(question: string, student: DemoStudent, schedule: ScheduleRow[], currentWeek: number): string {
  if (/成绩|分数|其他学生|别人|电话|手机号|身份证|导出|名单|请假|处分|心理/.test(question)) {
    return '学生账号只能查询本人课表，不能查询其他学生、成绩、联系方式或导出名单。';
  }
  const weekRows = schedule.filter((row) => weekMatches(row.weeks, currentWeek));
  if (!weekRows.length) {
    return `当前演示课表里没有你的排课数据（${student.class_short || student.class_name}）。请以教务处/青果为准。`;
  }
  const today = currentDayName();
  let day: string | null = today;
  let scopeLabel = '今天';
  if (question.includes('明天')) {
    day = nextDayName(today);
    scopeLabel = '明天';
  } else if (question.includes('本周') || question.includes('这周')) {
    day = null;
    scopeLabel = '本周';
  }

  let periods: string[] | null = null;
  let slotLabel = '';
  if (question.includes('下午')) {
    periods = ['5-6节', '7-8节'];
    slotLabel = '下午';
  } else if (question.includes('上午')) {
    periods = ['1-2节', '3-4节'];
    slotLabel = '上午';
  } else if (question.includes('晚上')) {
    periods = ['9-10节'];
    slotLabel = '晚上';
  }
  const single = question.match(/第\s*(\d+)\s*节/);
  if (single) {
    periods = weekRows.map((row) => row.period).filter((period) => period.includes(single[1]));
    slotLabel = `第${single[1]}节`;
  }
  if (periods && periods.length === 0) periods = null;

  if (day === null) {
    const lines = DAYS.map((item) => {
      const courses = weekRows
        .filter((row) => row.weekday === item && (!periods || periods.includes(periodSlot(row))))
        .sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : 0));
      return `${item}：${courses.length ? courses.map(courseLine).join('；') : '没有课'}`;
    });
    return `${scopeLabel}（第 ${currentWeek} 周）的安排：\n${lines.join('\n')}\n以青果/教务处课表为准。`;
  }

  const courses = weekRows
    .filter((row) => row.weekday === day && (!periods || periods.includes(periodSlot(row))))
    .sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : 0));
  const suffix = slotLabel ? `（${slotLabel}）` : '';
  if (!courses.length) {
    return `${scopeLabel}${suffix}没有课。按第 ${currentWeek} 周演示课表；最终以青果/教务处为准。`;
  }
  return `${scopeLabel}${suffix}有 ${courses.length} 门课：\n${courses.map(courseLine).join('\n')}\n按第 ${currentWeek} 周演示课表；最终以青果/教务处为准。`;
}

export default function StudentSchedulePage() {
  const { session, loading } = useSession();
  const { data, error } = useDemoData();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: '我是你的课表助手，只能看到你自己的课表。可以问我：今天下午有没有课、明天几节课、这周有哪些课。',
    },
  ]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);

  const student = useMemo(() => {
    const uid = session?.user.userName;
    if (!data || !uid) return null;
    return data.students.find((item) => item.uid === uid) ?? null;
  }, [data, session]);

  const mySchedule = useMemo(() => {
    if (!data || !student) return [];
    const keys = new Set([student.class_name, student.class_short].filter(Boolean));
    return data.schedule.filter((row) => keys.has(row.class_name) || keys.has(row.class_short));
  }, [data, student]);

  const currentWeek = data?.metrics.schedule_meta.current_week ?? 1;
  const periodTimes = data?.metrics.schedule_meta.period_times ?? [];
  const today = currentDayName();
  const weekSchedule = useMemo(
    () => mySchedule.filter((row) => weekMatches(row.weeks, currentWeek)),
    [mySchedule, currentWeek],
  );
  const periodOrder = periodTimes.map((item) => item.period);
  const sortByPeriod = (a: ScheduleRow, b: ScheduleRow) =>
    periodOrder.indexOf(a.period) - periodOrder.indexOf(b.period);
  const todayCourses = useMemo(
    () => weekSchedule.filter((row) => row.weekday === today).sort(sortByPeriod),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [weekSchedule, today, periodTimes],
  );
  const afternoon = todayCourses.filter((row) => ['5-6节', '7-8节'].includes(row.period));

  if (loading) {
    return <div className="wb wb-loading"><Spin size="large" /><span>正在读取学生身份…</span></div>;
  }

  if (error) {
    return <Alert type="error" showIcon message="课表数据加载失败" description={error} />;
  }

  if (!data) {
    return <div className="wb wb-loading"><Spin size="large" /><span>正在加载课表…</span></div>;
  }

  if (!student) {
    return (
      <Alert
        type="warning"
        showIcon
        message="当前账号不是学生演示账号"
        description="学生课表只对学生角色开放。请使用学生演示账号登录；管理员请从数据工作台预览排课数据。"
      />
    );
  }

  const send = (question: string) => {
    const text = question.trim();
    if (!text || thinking) return;
    setMessages((current) => [...current, { id: `u-${Date.now()}`, role: 'user', text }]);
    setInput('');
    setThinking(true);
    window.setTimeout(() => {
      const answer = buildScheduleAnswer(text, student, mySchedule, currentWeek);
      setMessages((current) => [...current, { id: `a-${Date.now()}`, role: 'assistant', text: answer }]);
      setThinking(false);
    }, 260);
  };

  return (
    <div className="wb ss">
      <PageHeader
        title="我的课表"
        description="学生视角：只显示本人班级课表和课表问答，不显示其他学生、成绩、联系方式，也不能导出名单。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">STUDENT VIEW</span>
            <span className="wb-badge is-demo">仅本人课表 · 演示数据</span>
          </div>
        }
      />

      <section className="wb-panel ss-profile">
        <div className="ss-avatar"><CalendarOutlined /></div>
        <div className="ss-profile-main">
          <b>{student.name}</b>
          <p>{student.college} · {student.major} · {student.class_short || student.class_name}</p>
          <small>UID {student.uid} · 辅导员 {student.counselor}</small>
        </div>
        <div className="ss-profile-meta">
          <Tag color="green">第 {currentWeek} 周</Tag>
          <span>{data.metrics.schedule_meta.note}</span>
        </div>
      </section>

      <div className="ss-layout">
        <div className="ss-left">
          <section className="wb-panel ss-today">
            <header className="wb-panel-head">
              <h2>今天 · {today}</h2>
              <span>{todayCourses.length} 门课 · 下午 {afternoon.length} 门</span>
            </header>
            {todayCourses.length ? (
              <div className="ss-today-list">
                {todayCourses.map((row) => (
                  <div className="ss-today-item" key={`${row.course}-${row.period}-${row.teacher}`}>
                    <b>{row.period}</b>
                    <span>{row.course}</span>
                    <small>{row.teacher || '教师待定'} · {row.room || row.note || '地点待定'}</small>
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="今天没有课" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
            <p className="wb-note">只显示本人班级课表；周次、作息时间以教务处/青果为准。</p>
          </section>

          <section className="wb-panel ss-week">
            <header className="wb-panel-head">
              <h2>本周课表</h2>
              <span>{fmt(mySchedule.length)} 条排课 · 第 {currentWeek} 周</span>
            </header>
            <div className="ss-table-wrap">
              <table className="ss-table">
                <thead>
                  <tr>
                    <th>节次</th>
                    {DAYS.map((day) => <th key={day} className={day === today ? 'is-today' : undefined}>{day}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {periodTimes.map((slot) => (
                    <tr key={slot.period}>
                      <th>
                        <b>{slot.period}</b>
                        <small>{slot.start}–{slot.end}</small>
                      </th>
                      {DAYS.map((day) => {
                        const courses = weekSchedule.filter((row) => row.weekday === day && row.period === slot.period);
                        return (
                          <td key={`${day}-${slot.period}`} className={day === today ? 'is-today' : undefined}>
                            {courses.length ? courses.map((row) => (
                              <div className="ss-course" key={`${row.course}-${row.teacher}-${row.room}`}>
                                <b>{row.course}</b>
                                <small>{row.teacher || '教师待定'}</small>
                                <span>{row.room || row.note || '地点待定'}</span>
                              </div>
                            )) : <span className="ss-empty">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="wb-note">演示按第 {currentWeek} 周显示；没有教室的课程显示备注（如校外实习/线上指导）。</p>
          </section>
        </div>

        <section className="wb-panel ss-ai">
          <header className="wb-panel-head">
            <h2>课表助手</h2>
            <span>只答本人课表 · 本地规则</span>
          </header>
          <div className="ai-messages ss-ai-messages">
            {messages.map((message) => (
              <div className={`ai-message is-${message.role}`} key={message.id}>
                <div className="ai-bubble"><p>{message.text}</p></div>
              </div>
            ))}
            {thinking ? <div className="ai-message is-assistant"><div className="ai-bubble ai-thinking">正在查你的课表…</div></div> : null}
          </div>
          <div className="ss-suggestions">
            {['今天下午有没有课？', '明天几节课？', '这周有哪些课？', '我的教室在哪？'].map((item) => (
              <button type="button" key={item} onClick={() => send(item)}>{item}</button>
            ))}
          </div>
          <div className="ai-input">
            <Input
              aria-label="课表提问"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={() => send(input)}
              placeholder="问：今天下午有没有课？"
              disabled={thinking}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={() => send(input)} loading={thinking}>问</Button>
          </div>
          <p className="wb-note">
            AI 通过你的 UID 绑定班级课表，只返回本人课表；不调用外部模型，不返回其他学生信息。
          </p>
        </section>
      </div>

      <p className="wb-footnote">{data.metrics.disclaimer} · 学生课表只读 · 课表来源：2026-2027-1 排课表</p>
    </div>
  );
}
