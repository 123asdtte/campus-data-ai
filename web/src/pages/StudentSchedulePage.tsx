import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Empty, Spin, Tag } from 'antd';
import { CalendarOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/ui';
import { fmt } from '../demo/format';
import type { ScheduleRow } from '../demo/types';
import {
  WEEKDAYS,
  currentDayName,
  normalizeWeekday,
  periodRank,
  weekMatches,
} from '../demo/schedule';
import { useDemoData } from '../demo/useDemoData';
import { useSession } from '../session/SessionContext';

interface FocusCell {
  weekday: string;
  period: string;
}

export default function StudentSchedulePage() {
  const { session, loading } = useSession();
  const { data, error } = useDemoData();
  const location = useLocation();
  const navigate = useNavigate();
  const [focusCell, setFocusCell] = useState<FocusCell | null>(null);
  const focusTimer = useRef<number>();

  const student = useMemo(() => {
    const uid = session?.user.userName;
    if (!data || !uid) return null;
    return data.students.find((item) => item.uid === uid) ?? null;
  }, [data, session]);

  const mySchedule = useMemo(() => {
    if (!data || !student) return [];
    const keys = new Set([student.class_name, student.class_short].filter(Boolean));
    return data.schedule
      .filter((row) => keys.has(row.class_name) || keys.has(row.class_short))
      .map((row) => ({ ...row, weekday: normalizeWeekday(row.weekday) }));
  }, [data, student]);

  const currentWeek = data?.metrics.schedule_meta.current_week ?? 1;
  const periodTimes = data?.metrics.schedule_meta.period_times ?? [];
  const today = currentDayName();
  const weekSchedule = useMemo(
    () => mySchedule.filter((row) => weekMatches(row.weeks, currentWeek)),
    [mySchedule, currentWeek],
  );
  const sortByPeriod = (a: ScheduleRow, b: ScheduleRow) => periodRank(a.period) - periodRank(b.period);
  const todayCourses = useMemo(
    () => weekSchedule.filter((row) => row.weekday === today).sort(sortByPeriod),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [weekSchedule, today],
  );
  const afternoon = todayCourses.filter((row) => ['5-6节', '7-8节'].includes(row.period));

  const applyFocus = useCallback((detail: FocusCell) => {
    if (!detail?.weekday || !detail?.period) return;
    setFocusCell(detail);
    window.setTimeout(() => {
      const cell = document.querySelector(
        `[data-weekday="${detail.weekday}"][data-period="${detail.period}"]`,
      );
      cell?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
    window.clearTimeout(focusTimer.current);
    focusTimer.current = window.setTimeout(() => setFocusCell(null), 5000);
  }, []);

  useEffect(() => {
    const onFocus = (event: Event) => {
      applyFocus((event as CustomEvent<FocusCell>).detail);
    };
    window.addEventListener('campus:focus-course', onFocus);
    return () => {
      window.removeEventListener('campus:focus-course', onFocus);
      window.clearTimeout(focusTimer.current);
    };
  }, [applyFocus]);

  useEffect(() => {
    const state = location.state as { focusCourse?: FocusCell } | null;
    if (!state?.focusCourse) return;
    applyFocus(state.focusCourse);
    navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

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

  return (
    <div className="wb ss">
      <PageHeader
        title="我的课表"
        description="只显示本人班级课表；课表问答在右下角 AI 助手中完成，结果可直接定位到对应课程。"
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

      <div className="ss-layout is-single">
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
                    {WEEKDAYS.map((day) => <th key={day} className={day === today ? 'is-today' : undefined}>{day}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {periodTimes.map((slot) => (
                    <tr key={slot.period}>
                      <th>
                        <b>{slot.period}</b>
                        <small>{slot.start}–{slot.end}</small>
                      </th>
                      {WEEKDAYS.map((day) => {
                        const courses = weekSchedule.filter((row) => row.weekday === day && row.period === slot.period);
                        const focused = focusCell?.weekday === day && focusCell?.period === slot.period;
                        return (
                          <td
                            key={`${day}-${slot.period}`}
                            data-weekday={day}
                            data-period={slot.period}
                            className={[day === today ? 'is-today' : '', focused ? 'is-focus' : ''].filter(Boolean).join(' ') || undefined}
                          >
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
      </div>

      <p className="wb-footnote">{data.metrics.disclaimer} · 学生课表只读 · 课表来源：2026-2027-1 排课表</p>
    </div>
  );
}
