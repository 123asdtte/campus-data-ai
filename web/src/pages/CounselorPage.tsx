import { useMemo, useState } from 'react';
import {
  Button,
  Empty,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DownloadOutlined, SearchOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/ui';
import { fmt, todayStamp } from '../demo/format';
import type { DemoData, DemoStudent } from '../demo/types';
import { useDemoData } from '../demo/useDemoData';
import { useSession } from '../session/SessionContext';

type CounselorClass = DemoData['class_summary'][number] & { keys: string[] };

const TONE_COLOR: Record<string, string> = {
  success: 'green',
  info: 'blue',
  warning: 'orange',
  danger: 'red',
  muted: 'default',
};

export default function CounselorPage() {
  const { data, error } = useDemoData();
  const { session } = useSession();
  const isCounselor = session?.roles.includes('counselor') ?? false;
  const boundCounselor = isCounselor ? session?.user.nickName ?? '' : '';
  const [counselor, setCounselor] = useState<string>('');
  const [classFilter, setClassFilter] = useState('all');
  const [keyword, setKeyword] = useState('');

  const counselors = useMemo(
    () => [...new Set((data?.class_summary ?? []).map((item) => item.counselor).filter(Boolean))].sort(),
    [data],
  );
  const currentCounselor = boundCounselor || counselor || counselors[0] || '';
  const classes = useMemo<CounselorClass[]>(() => {
    const grouped = new Map<string, CounselorClass>();
    for (const item of data?.class_summary ?? []) {
      if (item.counselor !== currentCounselor) continue;
      const keys = [item.class_name, item.class_short].filter(Boolean);
      const key = (item.class_short || item.class_name).replace(/\s+/g, '').replace(/班$/, '');
      const existing = grouped.get(key);
      if (existing) {
        existing.students += item.students;
        keys.forEach((value) => {
          if (!existing.keys.includes(value)) existing.keys.push(value);
        });
        Object.entries(item.status).forEach(([status, count]) => {
          existing.status[status] = (existing.status[status] ?? 0) + count;
        });
      } else {
        grouped.set(key, { ...item, keys: [...keys], status: { ...item.status } });
      }
    }
    return [...grouped.values()].sort((a, b) => a.class_name.localeCompare(b.class_name, 'zh-CN'));
  }, [data, currentCounselor]);
  const classKeys = useMemo(() => new Set(classes.flatMap((item) => item.keys)), [classes]);
  const students = useMemo(
    () => (data?.students ?? []).filter((student) => classKeys.has(student.class_name) || classKeys.has(student.class_short)),
    [data, classKeys],
  );

  const filtered = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    const selected = classFilter === 'all' ? null : classes.find((item) => item.class_name === classFilter);
    return students.filter((student) => {
      if (selected && !selected.keys.some((key) => key === student.class_name || key === student.class_short)) return false;
      if (q && !`${student.uid} ${student.name} ${student.major} ${student.class_short}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [students, classFilter, keyword]);

  if (error) {
    return <div className="wb"><Tag color="red">演示数据加载失败：{error}</Tag></div>;
  }

  if (!data) {
    return (
      <div className="wb wb-loading">
        <Spin size="large" />
        <span>正在加载本地演示数据…</span>
      </div>
    );
  }

  const active = students.filter((student) => student.is_active).length;
  const suspended = students.filter((student) => student.status === '休学').length;
  const withdrawn = students.filter((student) => student.status === '退学').length;
  const flagged = students.filter((student) => student.flags.length > 0).length;
  const changes = students.reduce((sum, student) => sum + student.change_count, 0);

  const exportRoster = () => {
    const headers = ['UID', '姓名（掩码）', '班级', '学籍状态', '本人电话', '数据标记'];
    const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
    const lines = filtered.map((student) =>
      [student.uid, student.name, student.class_short || student.class_name, student.status, student.phone, student.flags.join('、') || '无']
        .map(escape)
        .join(','),
    );
    const csv = `\uFEFF${[headers.map(escape).join(','), ...lines].join('\r\n')}`;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${currentCounselor}_带班名单_${todayStamp()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    void message.success(`已导出 ${fmt(filtered.length)} 名学生`);
  };

  const classColumns: ColumnsType<CounselorClass> = [
    {
      title: '班级',
      dataIndex: 'class_name',
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{row.class_short || value}</b>
          <small>{row.major}</small>
        </span>
      ),
    },
    {
      title: '学生数',
      dataIndex: 'students',
      width: 90,
      render: (value: number) => <b className="wb-mono">{fmt(value)}</b>,
    },
    {
      title: '状态分布',
      dataIndex: 'status',
      render: (value: Record<string, number>) => (
        <span className="wb-flags">
          {Object.entries(value).map(([key, count]) => (
            <span className="wb-flag" key={key}>{key} {count}</span>
          ))}
        </span>
      ),
    },
  ];

  const studentColumns: ColumnsType<DemoStudent> = [
    { title: 'UID', dataIndex: 'uid', width: 150, render: (value: string) => <span className="wb-mono">{value}</span> },
    {
      title: '学生',
      dataIndex: 'name',
      width: 110,
      render: (value: string, row) => <span>{value}<span className="wb-gender">{row.gender}</span></span>,
    },
    {
      title: '班级 / 专业',
      dataIndex: 'class_short',
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{value || row.class_name}</b>
          <small>{row.major}</small>
        </span>
      ),
    },
    {
      title: '学籍状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string, row) => <Tag color={TONE_COLOR[row.status_tone]}>{value}</Tag>,
    },
    { title: '电话', dataIndex: 'phone', width: 120, render: (value: string) => <span className="wb-mono">{value}</span> },
    {
      title: '标记',
      dataIndex: 'flags',
      render: (values: string[]) => values.length ? <span className="wb-flags">{values.map((item) => <span className="wb-flag" key={item}>{item}</span>)}</span> : <span className="wb-muted">—</span>,
    },
  ];

  return (
    <div className="wb">
      <PageHeader
        title="辅导员工作台"
        description="只看到自己带的班：班级、学生状态、缺字段与异动；一键导出本班名单。正式版由登录账号自动限定范围。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">SCOPE DEMO</span>
            <span className="wb-badge is-demo">演示身份切换 · 仅本班数据</span>
          </div>
        }
      />

      <div className="co-identity">
        {isCounselor ? (
          <>
            <span className="co-identity-label">当前登录辅导员</span>
            <b className="co-identity-bound">{boundCounselor}</b>
            <span className="co-identity-note">班级范围由登录账号绑定，页面不能切换身份。</span>
          </>
        ) : (
          <>
            <span className="co-identity-label">管理员预览</span>
            <Select
              showSearch
              value={currentCounselor}
              onChange={(value) => {
                setCounselor(value);
                setClassFilter('all');
                setKeyword('');
              }}
              style={{ width: 220 }}
              options={counselors.map((name) => ({ value: name, label: `辅导员 · ${name}` }))}
            />
            <span className="co-identity-note">仅管理员可预览其他辅导员；辅导员登录后自动锁定本人班级。</span>
          </>
        )}
      </div>

      <section className="wb-kpis">
        <div className="wb-kpi"><div className="wb-kpi-label">带班数</div><div className="wb-kpi-value">{classes.length}</div><div className="wb-kpi-hint">{currentCounselor}</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">学生数</div><div className="wb-kpi-value">{fmt(students.length)}</div><div className="wb-kpi-hint">在籍 {fmt(active)}</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">休学 / 退学</div><div className="wb-kpi-value">{suspended} <em>/</em> {withdrawn}</div><div className="wb-kpi-hint">需跟踪</div></div>
        <div className="wb-kpi is-warn"><div className="wb-kpi-label">有数据标记</div><div className="wb-kpi-value">{fmt(flagged)}</div><div className="wb-kpi-hint">缺字段 / 身份证 / 班级</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">异动记录</div><div className="wb-kpi-value">{fmt(changes)}</div><div className="wb-kpi-hint">本班学生累计</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">数据范围</div><div className="wb-kpi-value">本班</div><div className="wb-kpi-hint">不跨班、不跨学院</div></div>
      </section>

      <div className="wb-grid co-grid">
        <section className="wb-panel">
          <header className="wb-panel-head"><h2>我的班级</h2><span>{classes.length} 个班 · 名称变体已归并</span></header>
          <Table
            rowKey="class_name"
            size="small"
            columns={classColumns}
            dataSource={classes}
            pagination={false}
            onRow={(record) => ({ onClick: () => setClassFilter(record.class_name) })}
            rowClassName={() => 'wb-row'}
            locale={{ emptyText: <Empty description="暂无带班数据" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
          />
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head"><h2>本班待办</h2><span>按当前演示身份</span></header>
          <div className="co-todo">
            <div><b>{fmt(flagged)}</b><span>学生有缺失/异常标记，建议补录或核对</span></div>
            <div><b>{fmt(suspended)}</b><span>学生休学，需跟进复学或保留学籍</span></div>
            <div><b>{fmt(withdrawn)}</b><span>学生退学，核对离校与档案状态</span></div>
            <div><b>{fmt(changes)}</b><span>条异动记录，可在“学籍异动”中查看详情</span></div>
          </div>
          <p className="wb-note">正式版这里会按角色显示待办、审批和提醒；演示版为只读汇总。</p>
        </section>
      </div>

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head"><h2>本班学生</h2><span>仅显示 UID 与脱敏字段</span></header>
        <div className="wb-toolbar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="UID / 姓名 / 专业" value={keyword} onChange={(event) => setKeyword(event.target.value)} style={{ width: 240 }} />
          <Select
            value={classFilter}
            onChange={setClassFilter}
            style={{ width: 200 }}
            options={[{ value: 'all', label: '全部班级' }, ...classes.map((item) => ({ value: item.class_name, label: item.class_short || item.class_name }))]}
          />
          <Button icon={<DownloadOutlined />} onClick={exportRoster}>导出本班名单</Button>
          <span className="wb-result-count">命中 {fmt(filtered.length)} 人</span>
        </div>
        <Table<DemoStudent>
          rowKey="uid"
          size="middle"
          columns={studentColumns}
          dataSource={filtered}
          scroll={{ x: 980 }}
          pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (total) => `共 ${fmt(total)} 人` }}
          locale={{ emptyText: <Empty description="没有匹配的学生" /> }}
        />
      </section>

      <p className="wb-footnote">{data.metrics.disclaimer} · 辅导员范围演示 · 导出仅含本班脱敏字段</p>
    </div>
  );
}
