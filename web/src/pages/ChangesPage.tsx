import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Spin,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, SearchOutlined, SwapOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/ui';
import { fmt, todayStamp } from '../demo/format';
import type { DemoChange, DemoStudent } from '../demo/types';
import { useDemoData } from '../demo/useDemoData';

interface ChangeRow {
  key: string;
  change_no: string;
  uid: string;
  name: string;
  college: string;
  class_name: string;
  type: string;
  date: string;
  reason: string;
  target: string;
  status: string;
  student_status: string;
}

interface AuditEntry {
  time: string;
  action: string;
  detail: string;
}

const CHANGE_TYPES = ['休学', '复学', '退学', '转专业', '保留学籍', '跟读生转正式', '预科生转正', '留级'];

const STATUS_BY_TYPE: Record<string, string> = {
  休学: '休学',
  复学: '在籍',
  退学: '退学',
  保留学籍: '保留学籍',
  跟读生转正式: '在籍',
  预科生转正: '在籍',
};

function tone(status: string): string {
  if (status.includes('已批')) return 'green';
  if (status.includes('退回')) return 'red';
  return 'orange';
}

function toCsv(rows: ChangeRow[]): string {
  const headers = ['UID', '姓名（掩码）', '二级学院', '班级', '异动类型', '异动日期', '审批状态', '去向'];
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const lines = rows.map((row) =>
    [row.uid, row.name, row.college, row.class_name, row.type, row.date, row.status, row.target]
      .map((value) => escape(value))
      .join(','),
  );
  return `\uFEFF${[headers.map(escape).join(','), ...lines].join('\r\n')}`;
}

export default function ChangesPage() {
  const { data, error } = useDemoData();
  const [changes, setChanges] = useState<DemoChange[]>([]);
  const [statusOverrides, setStatusOverrides] = useState<Record<string, string>>({});
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [keyword, setKeyword] = useState('');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('all');
  const [college, setCollege] = useState('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    if (data) setChanges(data.changes);
  }, [data]);

  const studentMap = useMemo(() => {
    const map = new Map<string, DemoStudent>();
    data?.students.forEach((student) => map.set(student.uid, student));
    return map;
  }, [data]);

  const rows = useMemo<ChangeRow[]>(
    () =>
      changes
        .map((change) => {
          const student = studentMap.get(change.uid);
          return {
            key: change.change_no,
            change_no: change.change_no,
            uid: change.uid,
            name: student?.name ?? '—',
            college: student?.college ?? '—',
            class_name: student?.class_short || student?.class_name || '—',
            type: change.type,
            date: change.date,
            reason: change.reason,
            target: change.target,
            status: change.status,
            student_status: statusOverrides[change.uid] ?? student?.status ?? '—',
          };
        })
        .sort((a, b) => {
          const aLocal = a.change_no.startsWith('YD-LOCAL') ? 1 : 0;
          const bLocal = b.change_no.startsWith('YD-LOCAL') ? 1 : 0;
          if (aLocal !== bLocal) return bLocal - aLocal;
          const aPending = a.status.includes('审批中') ? 1 : 0;
          const bPending = b.status.includes('审批中') ? 1 : 0;
          if (aPending !== bPending) return bPending - aPending;
          return a.date < b.date ? 1 : a.date > b.date ? -1 : 0;
        }),
    [changes, studentMap, statusOverrides],
  );

  const filtered = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    return rows.filter((row) => {
      if (type !== 'all' && row.type !== type) return false;
      if (status !== 'all' && row.status !== status) return false;
      if (college !== 'all' && row.college !== college) return false;
      if (q && !`${row.uid} ${row.name} ${row.class_name} ${row.change_no}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [rows, keyword, type, status, college]);

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

  const types = [...new Set(rows.map((row) => row.type))];
  const statuses = [...new Set(rows.map((row) => row.status))];
  const colleges = data.metrics.college_counts.map((item) => item.name);
  const pending = rows.filter((row) => row.status.includes('审批中')).length;
  const approved = rows.filter((row) => row.status.includes('已批')).length;

  const addAudit = (action: string, detail: string) => {
    setAudit((current) => [
      { time: new Date().toLocaleString('zh-CN', { hour12: false }), action, detail },
      ...current,
    ].slice(0, 6));
  };

  const confirmChange = (row: ChangeRow) => {
    setChanges((current) =>
      current.map((change) =>
        change.change_no === row.change_no ? { ...change, status: '已批' } : change,
      ),
    );
    const nextStatus = STATUS_BY_TYPE[row.type];
    if (nextStatus) {
      setStatusOverrides((current) => ({ ...current, [row.uid]: nextStatus }));
    }
    addAudit('教务确认', `${row.change_no} ${row.type} → ${nextStatus || '状态不变'}`);
    void message.success(`${row.change_no} 已确认，学生状态${nextStatus ? `更新为「${nextStatus}」` : '不变'}`);
  };

  const submitChange = async () => {
    try {
      const values = await form.validateFields();
      const student = studentMap.get(values.uid);
      if (!student) return;
      const next: DemoChange = {
        uid: values.uid,
        change_no: `YD-LOCAL-${Date.now().toString().slice(-6)}`,
        type: values.type,
        date: values.date,
        reason: values.reason,
        target: values.target || '—',
        status: '审批中',
      };
      setChanges((current) => [next, ...current]);
      addAudit('发起异动', `${next.uid} ${next.type}（${next.date}）`);
      setModalOpen(false);
      form.resetFields();
      void message.success(`已发起 ${next.type}，等待教务确认（本地演示）`);
    } catch {
      // Ant Design 会在表单上展示校验错误
    }
  };

  const exportChanges = () => {
    const blob = new Blob([toCsv(filtered)], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `学籍异动清单_${todayStamp()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    void message.success(`已导出 ${fmt(filtered.length)} 条异动`);
  };

  const columns: ColumnsType<ChangeRow> = [
    { title: '异动编号', dataIndex: 'change_no', width: 150, render: (value: string) => <span className="wb-mono">{value}</span> },
    {
      title: '学生',
      dataIndex: 'name',
      width: 150,
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{row.uid}</b>
          <small>{value} · {row.student_status}</small>
        </span>
      ),
    },
    { title: '类型', dataIndex: 'type', width: 110, render: (value: string) => <Tag>{value}</Tag> },
    {
      title: '学院 / 班级',
      dataIndex: 'college',
      width: 200,
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{value}</b>
          <small>{row.class_name}</small>
        </span>
      ),
    },
    { title: '异动日期', dataIndex: 'date', width: 110, render: (value: string) => <span className="wb-mono">{value}</span> },
    {
      title: '原因 / 去向',
      dataIndex: 'reason',
      width: 240,
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{value || '未填原因'}</b>
          <small>{row.target}</small>
        </span>
      ),
    },
    {
      title: '审批状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag color={tone(value)}>{value}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 110,
      render: (_, row) =>
        row.status.includes('审批中') ? (
          <Button size="small" type="link" onClick={() => confirmChange(row)}>
            教务确认
          </Button>
        ) : (
          <span className="wb-muted">—</span>
        ),
    },
  ];

  const maxType = Math.max(1, ...types.map((item) => rows.filter((row) => row.type === item).length));

  return (
    <div className="wb">
      <PageHeader
        title="学籍异动"
        description="辅导员登记异动，教务确认后联动学籍状态；所有操作留在本地演示记录里，不写正式库。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">LOCAL DEMO</span>
            <span className="wb-badge is-demo">演示数据 · 不写正式库</span>
          </div>
        }
      />

      <section className="wb-kpis ch-kpis">
        <div className="wb-kpi"><div className="wb-kpi-label">异动总数</div><div className="wb-kpi-value">{fmt(rows.length)}</div><div className="wb-kpi-hint">工作台 {data.metrics.change_total} 条 · {data.metrics.orphan_changes} 条学号未匹配</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">待教务确认</div><div className="wb-kpi-value">{fmt(pending)}</div><div className="wb-kpi-hint">含新增与初始待审</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">已批</div><div className="wb-kpi-value">{fmt(approved)}</div><div className="wb-kpi-hint">状态已联动</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">异动类型</div><div className="wb-kpi-value">{types.length}</div><div className="wb-kpi-hint">休学 / 退学 / 转专业等</div></div>
      </section>

      <div className="wb-grid ch-grid">
        <section className="wb-panel">
          <header className="wb-panel-head"><h2>异动类型分布</h2><span>本地记录</span></header>
          <div className="wb-chart-list">
            {types.map((item) => {
              const count = rows.filter((row) => row.type === item).length;
              return (
                <div className="wb-chart-row" key={item}>
                  <span className="wb-chart-label">{item}</span>
                  <span className="wb-chart-track"><span className="wb-chart-fill" style={{ width: `${(count / maxType) * 100}%`, background: 'var(--warning)' }} /></span>
                  <span className="wb-chart-value">{fmt(count)}</span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head"><h2>操作记录</h2><span>本地演示 · 最近 6 条</span></header>
          {audit.length ? (
            <div className="rp-log-list">
              {audit.map((item, index) => (
                <div className="rp-log" key={`${item.time}-${index}`}>
                  <span>{item.time}</span>
                  <b>{item.action}</b>
                  <small>{item.detail}</small>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="还没有本地操作；发起一次异动试试" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
          <p className="wb-note">正式版会把发起、确认、退回写入审计表；演示版刷新页面即重置。</p>
        </section>
      </div>

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head"><h2>异动台账</h2><span>点击“教务确认”演示状态联动</span></header>
        <div className="wb-toolbar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="异动编号 / UID / 班级" value={keyword} onChange={(e) => setKeyword(e.target.value)} style={{ width: 230 }} />
          <Select value={type} onChange={setType} style={{ width: 150 }} options={[{ value: 'all', label: '全部类型' }, ...types.map((item) => ({ value: item, label: item }))]} />
          <Select value={status} onChange={setStatus} style={{ width: 150 }} options={[{ value: 'all', label: '全部审批状态' }, ...statuses.map((item) => ({ value: item, label: item }))]} />
          <Select value={college} onChange={setCollege} style={{ width: 170 }} options={[{ value: 'all', label: '全部学院' }, ...colleges.map((item) => ({ value: item, label: item }))]} />
          <Button icon={<SwapOutlined />} onClick={exportChanges}>导出异动清单</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>发起异动</Button>
          <span className="wb-result-count">命中 {fmt(filtered.length)} 条</span>
        </div>
        <Table<ChangeRow>
          rowKey="key"
          size="middle"
          columns={columns}
          dataSource={filtered}
          scroll={{ x: 1160 }}
          pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (total) => `共 ${fmt(total)} 条` }}
          locale={{ emptyText: <Empty description="没有匹配的异动记录" /> }}
        />
      </section>

      <p className="wb-footnote">{data.metrics.disclaimer} · 异动流程为本地演示，不写正式库</p>

      <Modal
        title="发起学籍异动"
        open={modalOpen}
        onOk={submitChange}
        okText="提交（待教务确认）"
        cancelText="取消"
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" initialValues={{ type: '休学', date: new Date().toISOString().slice(0, 10) }}>
          <Form.Item name="uid" label="学生" rules={[{ required: true, message: '请选择学生' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="按 UID / 姓名 / 班级搜索"
              options={data.students.map((student) => ({
                value: student.uid,
                label: `${student.uid} · ${student.name} · ${student.class_short || student.class_name}`,
              }))}
            />
          </Form.Item>
          <div className="ch-form-row">
            <Form.Item name="type" label="异动类型" rules={[{ required: true }]}><Select options={CHANGE_TYPES.map((item) => ({ value: item, label: item }))} /></Form.Item>
            <Form.Item name="date" label="异动日期" rules={[{ required: true }]}><Input type="date" /></Form.Item>
          </div>
          <Form.Item name="reason" label="异动原因" rules={[{ required: true, message: '请填写原因' }]}><Input.TextArea rows={2} placeholder="如：身体原因 / 新生转专业（笔试面试通过）" /></Form.Item>
          <Form.Item name="target" label="异动后去向（可选）"><Input placeholder="如：转入汽车工程学院新能源汽车检测与维修技术2601" /></Form.Item>
        </Form>
        <p className="wb-note">提交后进入“审批中”；点击台账里的“教务确认”才会更新学生状态。本地演示不写正式库。</p>
      </Modal>
    </div>
  );
}
