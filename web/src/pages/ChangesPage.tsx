import { useEffect, useMemo, useRef, useState } from 'react';
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
import { PlusOutlined, SearchOutlined, SwapOutlined, UploadOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/ui';
import { useSession } from '../session/SessionContext';
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
  platform_status: string;
  student_status: string;
}

interface AuditEntry {
  time: string;
  action: string;
  detail: string;
}

const CHANGE_TYPES = ['休学', '复学', '退学', '转专业', '保留学籍', '跟读生转正式', '预科生转正', '留级'];

function tone(status: string): string {
  if (status.includes('已批')) return 'green';
  if (status.includes('退回')) return 'red';
  return 'orange';
}

function toCsv(rows: ChangeRow[]): string {
  const headers = ['UID', '姓名（掩码）', '二级学院', '班级', '异动类型', '异动日期', '正式审批（源表）', '平台核对', '去向'];
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const lines = rows.map((row) =>
    [row.uid, row.name, row.college, row.class_name, row.type, row.date, row.status, row.platform_status, row.target]
      .map((value) => escape(value))
      .join(','),
  );
  return `\uFEFF${[headers.map(escape).join(','), ...lines].join('\r\n')}`;
}

export default function ChangesPage() {
  const { data, error } = useDemoData();
  const { session } = useSession();
  const isCounselor = session?.roles.includes('counselor') ?? false;
  const counselorName = isCounselor ? session?.user.nickName ?? '' : '';
  const [changes, setChanges] = useState<DemoChange[]>([]);
  const [platformChecked, setPlatformChecked] = useState<Set<string>>(new Set());
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [keyword, setKeyword] = useState('');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('all');
  const [college, setCollege] = useState('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!data) return;
    setChanges(data.changes);
    setPlatformChecked(new Set(data.changes.filter((change) => change.status.includes('已批')).map((change) => change.change_no)));
  }, [data]);

  const studentMap = useMemo(() => {
    const map = new Map<string, DemoStudent>();
    data?.students.forEach((student) => map.set(student.uid, student));
    return map;
  }, [data]);

  const scopedUids = useMemo(() => {
    if (!isCounselor || !data) return null;
    const keys = new Set(
      data.class_summary
        .filter((item) => item.counselor === counselorName)
        .flatMap((item) => [item.class_name, item.class_short]),
    );
    return new Set(
      data.students
        .filter((student) => keys.has(student.class_name) || keys.has(student.class_short))
        .map((student) => student.uid),
    );
  }, [data, isCounselor, counselorName]);

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
            platform_status: platformChecked.has(change.change_no) ? '已核对' : '待核对',
            student_status: student?.status ?? '—',
          };
        })
        .filter((row) => !scopedUids || scopedUids.has(row.uid))
        .sort((a, b) => {
          const aLocal = a.change_no.startsWith('YD-LOCAL') ? 1 : 0;
          const bLocal = b.change_no.startsWith('YD-LOCAL') ? 1 : 0;
          if (aLocal !== bLocal) return bLocal - aLocal;
          const aPending = a.status.includes('审批中') ? 1 : 0;
          const bPending = b.status.includes('审批中') ? 1 : 0;
          if (aPending !== bPending) return bPending - aPending;
          return a.date < b.date ? 1 : a.date > b.date ? -1 : 0;
        }),
    [changes, studentMap, platformChecked, scopedUids],
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
  const pending = rows.filter((row) => row.platform_status === '待核对').length;
  const approved = rows.filter((row) => row.platform_status === '已核对').length;

  const addAudit = (action: string, detail: string) => {
    setAudit((current) => [
      { time: new Date().toLocaleString('zh-CN', { hour12: false }), action, detail },
      ...current,
    ].slice(0, 6));
  };

  const markChecked = (row: ChangeRow) => {
    setPlatformChecked((current) => {
      const next = new Set(current);
      next.add(row.change_no);
      return next;
    });
    addAudit('平台核对', `${row.change_no} ${row.type}`);
    void message.success(`${row.change_no} 已标记平台核对；正式审批状态不变`);
  };

  const importWorkbook = async (file: File) => {
    try {
      const XLSX = await import('xlsx');
      const buffer = await file.arrayBuffer();
      const workbook = XLSX.read(buffer, { type: 'array' });
      const sheet = workbook.Sheets[workbook.SheetNames[0]];
      const records = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
      const normalizeDate = (value: unknown): string => {
        if (typeof value === 'number') {
          const parsed = XLSX.SSF.parse_date_code(value);
          if (parsed) return `${parsed.y}-${String(parsed.m).padStart(2, '0')}-${String(parsed.d).padStart(2, '0')}`;
        }
        return String(value ?? '').trim();
      };
      const existing = new Set(changes.map((item) => item.change_no));
      const imported: DemoChange[] = [];
      let skipped = 0;
      records.forEach((row, index) => {
        const uid = String(row.UID ?? row.uid ?? '').trim();
        if (!studentMap.has(uid) || (scopedUids && !scopedUids.has(uid))) {
          skipped += 1;
          return;
        }
        const baseNo = String(row['异动编号'] ?? row['编号'] ?? `IMP-${Date.now()}-${index + 1}`).trim();
        const changeNo = existing.has(baseNo) ? `${baseNo}-IMP${index + 1}` : baseNo;
        existing.add(changeNo);
        imported.push({
          uid,
          change_no: changeNo,
          type: String(row['异动类型'] ?? row['类型'] ?? '其他').trim() || '其他',
          date: normalizeDate(row['异动日期'] ?? row['日期']),
          reason: String(row['异动原因'] ?? row['原因'] ?? '').trim(),
          target: String(row['异动后去向'] ?? row['去向'] ?? '—').trim() || '—',
          status: String(row['正式审批状态'] ?? row['审批状态'] ?? '审批中').trim() || '审批中',
        });
      });
      if (imported.length) {
        setChanges((current) => [...imported, ...current]);
        addAudit('导入异动', `${file.name} · 导入 ${imported.length} 条 · 跳过 ${skipped} 条`);
        void message.success(`已导入 ${imported.length} 条异动${skipped ? `，跳过 ${skipped} 条无匹配 UID 的记录` : ''}`);
      } else {
        void message.warning(`没有导入记录；请检查模板中的 UID。跳过 ${skipped} 条。`);
      }
    } catch (reason) {
      void message.error(`导入失败：${reason instanceof Error ? reason.message : '文件无法解析'}`);
    }
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
          <small>{value} · 学籍：{row.student_status}</small>
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
      title: '正式审批（源表）',
      dataIndex: 'status',
      width: 120,
      render: (value: string) => <Tag color={tone(value)}>{value}</Tag>,
    },
    {
      title: '平台核对',
      dataIndex: 'platform_status',
      width: 100,
      render: (value: string) => <Tag color={value === '已核对' ? 'green' : 'orange'}>{value}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 110,
      render: (_, row) =>
        row.platform_status !== '已核对' ? (
          <Button size="small" type="link" onClick={() => markChecked(row)}>
            平台核对
          </Button>
        ) : (
          <span className="wb-muted">已核对</span>
        ),
    },
  ];

  const maxType = Math.max(1, ...types.map((item) => rows.filter((row) => row.type === item).length));

  return (
    <div className="wb">
      <PageHeader
        title="学籍异动"
        description={isCounselor ? '只显示本人所带班级的异动台账；正式审批仍在青果或线下，本页只做登记与平台核对。' : '辅导员登记/导入异动，学工处做平台核对；正式审批仍在青果或线下，本页只做台账与核对，不改变正式学籍状态。'}
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">LOCAL DEMO</span>
            <span className="wb-badge is-demo">演示数据 · 不写正式库</span>
          </div>
        }
      />

      <section className="wb-kpis ch-kpis">
        <div className="wb-kpi"><div className="wb-kpi-label">异动总数</div><div className="wb-kpi-value">{fmt(rows.length)}</div><div className="wb-kpi-hint">工作台 {data.metrics.change_total} 条 · {data.metrics.orphan_changes} 条学号未匹配</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">待平台核对</div><div className="wb-kpi-value">{fmt(pending)}</div><div className="wb-kpi-hint">正式审批状态另列</div></div>
        <div className="wb-kpi"><div className="wb-kpi-label">平台已核对</div><div className="wb-kpi-value">{fmt(approved)}</div><div className="wb-kpi-hint">不改变源系统审批</div></div>
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
          <p className="wb-note">导入模板使用 UID；正式版由后端按学号 → UID 映射并校验权限。演示版刷新页面即重置。</p>
        </section>
      </div>

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head"><h2>异动台账</h2><span>平台核对与源表正式审批分开显示 · 支持 Excel 导入</span></header>
        <div className="wb-toolbar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="异动编号 / UID / 班级" value={keyword} onChange={(e) => setKeyword(e.target.value)} style={{ width: 230 }} />
          <Select value={type} onChange={setType} style={{ width: 150 }} options={[{ value: 'all', label: '全部类型' }, ...types.map((item) => ({ value: item, label: item }))]} />
          <Select value={status} onChange={setStatus} style={{ width: 170 }} options={[{ value: 'all', label: '全部正式审批状态' }, ...statuses.map((item) => ({ value: item, label: item }))]} />
          <Select value={college} onChange={setCollege} style={{ width: 170 }} options={[{ value: 'all', label: '全部学院' }, ...colleges.map((item) => ({ value: item, label: item }))]} />
          <Button icon={<SwapOutlined />} onClick={exportChanges}>导出异动清单</Button>
          <Button icon={<UploadOutlined />} onClick={() => fileInput.current?.click()}>导入 Excel</Button>
          <a className="wb-download" href="/demo/change-import-template.csv" download>下载导入模板</a>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>发起异动</Button>
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx,.xls,.csv"
            style={{ display: 'none' }}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importWorkbook(file);
              event.currentTarget.value = '';
            }}
          />
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
        okText="提交（待平台核对）"
        cancelText="取消"
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" initialValues={{ type: '休学', date: new Date().toISOString().slice(0, 10) }}>
          <Form.Item name="uid" label="学生" rules={[{ required: true, message: '请选择学生' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="按 UID / 姓名 / 班级搜索"
              options={data.students
                .filter((student) => !scopedUids || scopedUids.has(student.uid))
                .map((student) => ({
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
        <p className="wb-note">提交后进入“待平台核对”；正式审批仍在青果/线下完成。本地演示不写正式库，也不回写源系统。</p>
      </Modal>
    </div>
  );
}
