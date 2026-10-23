import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, DatePicker, Empty, Input, Select, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { ApiError } from '../api/client';
import { fetchAuditLogs, fetchAuditSummary } from '../api/audit';
import type { AuditLogEntry, AuditQuery, AuditSummaryItem } from '../api/types';
import { Panel, PageHeader } from '../components/ui';

const ACTION_LABEL: Record<AuditLogEntry['action'], string> = {
  insert: '新增',
  update: '修改',
  delete: '删除',
};

function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-');
}

function fmtVal(value: unknown): string {
  if (value === null || value === undefined) return '空';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function AuditPage() {
  const [keyword, setKeyword] = useState('');
  const [debounced, setDebounced] = useState('');
  const [actor, setActor] = useState<string | undefined>();
  const [action, setAction] = useState<string | undefined>();
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [rows, setRows] = useState<AuditLogEntry[]>([]);
  const [summary, setSummary] = useState<AuditSummaryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(keyword.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const fromDate = range ? range[0].format('YYYY-MM-DD') : undefined;
    const untilDate = range ? range[1].add(1, 'day').format('YYYY-MM-DD') : undefined;
    try {
      const query: AuditQuery = {
        keyword: debounced || undefined,
        actor,
        action,
        from_date: fromDate,
        until_date: untilDate,
        page,
        page_size: pageSize,
      };
      const [result, summaryRes] = await Promise.all([
        fetchAuditLogs(query),
        fetchAuditSummary({ from_date: fromDate, until_date: untilDate }).catch(() => ({ items: [] })),
      ]);
      setRows(result.items);
      setTotal(result.total);
      setSummary(summaryRes.items);
    } catch (err) {
      setRows([]);
      setTotal(0);
      setError((err as ApiError).message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [debounced, actor, action, range, page, pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        title="操作审计"
        description="全校所有字段级编辑留痕（含操作人、动作、修改前后），由数据库触发器自动写入，不可篡改。"
      />
      <PanelAudit error={error} onRetry={load} />
      <div className="filter-bar" style={{ marginTop: 12 }}>
        <div className="field is-grow">
          <span className="field-label">学号/姓名</span>
          <Input
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--faint)' }} />}
            placeholder="检索被操作的学生"
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="field">
          <span className="field-label">操作人</span>
          <Input
            allowClear
            placeholder="如 demo-teacher"
            style={{ width: 180 }}
            value={actor}
            onChange={(e) => {
              setActor(e.target.value || undefined);
              setPage(1);
            }}
          />
        </div>
        <div className="field">
          <span className="field-label">动作</span>
          <Select
            allowClear
            placeholder="全部"
            style={{ width: 120 }}
            value={action}
            onChange={(v) => {
              setAction(v);
              setPage(1);
            }}
            options={[
              { label: '新增', value: 'insert' },
              { label: '修改', value: 'update' },
              { label: '删除', value: 'delete' },
            ]}
          />
        </div>
        <div className="field">
          <span className="field-label">时间区间</span>
          <DatePicker.RangePicker
            style={{ width: 260 }}
            value={range}
            allowClear
            onChange={(v) => {
              setRange(v as [Dayjs, Dayjs] | null);
              setPage(1);
            }}
          />
        </div>
        <div className="filter-actions">
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <PanelAuditTable
        rows={rows}
        total={total}
        loading={loading}
        page={page}
        pageSize={pageSize}
        onChange={(p, s) => {
          setPage(p);
          setPageSize(s);
        }}
      />

      <div style={{ marginTop: 16 }}>
        <Panel
          title="操作人统计"
          sub="按时间区间汇总各操作人的增/改/删次数"
          flush
        >
          {summary.length === 0 ? (
            <div className="cell-muted" style={{ padding: '12px 4px' }}>当前筛选条件下暂无操作记录</div>
          ) : (
            <Table<AuditSummaryItem>
              rowKey="display_name"
              size="small"
              pagination={false}
              dataSource={summary}
              columns={[
                {
                  title: '操作人',
                  dataIndex: 'display_name',
                  width: 200,
                  render: (v: string) => <span className="mono">{v}</span>,
                },
                { title: '总次数', dataIndex: 'total', width: 100, align: 'right' },
                { title: '新增', dataIndex: 'inserts', width: 90, align: 'right',
                  render: (v: number) => <span style={{ color: 'var(--ink)' }}>{v}</span> },
                { title: '修改', dataIndex: 'updates', width: 90, align: 'right' },
                { title: '删除', dataIndex: 'deletes', width: 90, align: 'right' },
              ]}
            />
          )}
        </Panel>
      </div>
    </>
  );
}

function PanelAudit({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  if (!error) return null;
  return (
    <Alert
      style={{ marginTop: 12 }}
      type="error"
      showIcon
      message="加载失败"
      description={error}
      action={<Button size="small" onClick={onRetry}>重试</Button>}
    />
  );
}

function PanelAuditTable({
  rows,
  total,
  loading,
  page,
  pageSize,
  onChange,
}: {
  rows: AuditLogEntry[];
  total: number;
  loading: boolean;
  page: number;
  pageSize: number;
  onChange: (p: number, s: number) => void;
}) {
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <Table<AuditLogEntry>
        rowKey="id"
        columns={columnsDef()}
        dataSource={rows}
        loading={loading}
        scroll={{ x: 1100 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100],
          showTotal: (value) => `共 ${value} 条`,
          onChange,
        }}
        locale={{ emptyText: <Empty description="暂无操作记录" /> }}
      />
    </div>
  );
}

function columnsDef(): ColumnsType<AuditLogEntry> {
  // 与上层 columns 相同，独立返回以适配分页面板的类型要求
  return [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 168,
      render: (v: string) => <span className="cell-muted mono">{formatTime(v)}</span>,
    },
    {
      title: '操作人',
      dataIndex: 'actor_user_id',
      width: 140,
      render: (v: string | null, r: AuditLogEntry) => <span className="mono">{v || r.actor_db_role}</span>,
    },
    {
      title: '动作',
      dataIndex: 'action',
      width: 72,
      render: (v: AuditLogEntry['action']) => ACTION_LABEL[v] ?? v,
    },
    {
      title: '对象',
      key: 'object',
      width: 200,
      render: (_: unknown, r: AuditLogEntry) =>
        r.object_type === 'students' ? (
          <span>
            <span className="mono">{r.student_no ?? '—'}</span>
            <span style={{ marginLeft: 6 }}>{r.student_name ?? ''}</span>
          </span>
        ) : (
          <span className="cell-muted">{r.object_type}</span>
        ),
    },
    {
      title: '变更字段',
      dataIndex: 'changed_fields',
      width: 150,
      render: (v: string[] | null) => (v && v.length ? v.join('、') : '—'),
    },
    {
      title: '变更明细（修改前 → 修改后）',
      key: 'detail',
      render: (_: unknown, r: AuditLogEntry) => {
        const fields = r.changed_fields ?? [];
        if (!fields.length) return '—';
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {fields.map((f: string) => (
              <div key={f} style={{ fontSize: 12 }}>
                <span className="mono" style={{ color: 'var(--muted)' }}>{f}</span>：{' '}
                <span className="cell-muted mono">{fmtVal(r.before_data?.[f])}</span>
                {' → '}
                <span className="mono">{fmtVal(r.after_data?.[f])}</span>
              </div>
            ))}
          </div>
        );
      },
    },
  ];
}
