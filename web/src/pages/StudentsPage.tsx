import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Select,
  Switch,
  Table,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { ApiError } from '../api/client';
import { fetchFilterOptions, fetchStudent, fetchStudents } from '../api/students';
import type { FilterOptions, Student, StudentChange, StudentDetail, StudentStatus } from '../api/types';
import { CHANGE_TYPE_LABEL, RECORD_STATUS_LABEL, STUDENT_STATUS_LABEL } from '../api/types';
import { EmptyState, PageHeader, Panel, StatTile, StatusBadge } from '../components/ui';

const STATUS_TONE: Record<StudentStatus, 'success' | 'warning' | 'danger' | 'info' | 'muted'> = {
  enrolled: 'success',
  suspended: 'warning',
  withdrawn: 'danger',
  graduated: 'info',
  other: 'muted',
};

function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-');
}

export default function StudentsPage() {
  const [keyword, setKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [college, setCollege] = useState<string | undefined>();
  const [className, setClassName] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [includeInactive, setIncludeInactive] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [rows, setRows] = useState<Student[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterOptions | null>(null);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<StudentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedKeyword(keyword.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  useEffect(() => {
    fetchFilterOptions()
      .then(setFilters)
      .catch(() => setFilters(null));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchStudents({
        keyword: debouncedKeyword || undefined,
        college,
        class_name: className,
        status,
        include_inactive: includeInactive,
        page,
        page_size: pageSize,
      });
      setRows(result.items);
      setTotal(result.total);
    } catch (err) {
      setRows([]);
      setTotal(0);
      setError((err as ApiError).message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [debouncedKeyword, college, className, status, includeInactive, page, pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  const resetFilters = () => {
    setKeyword('');
    setDebouncedKeyword('');
    setCollege(undefined);
    setClassName(undefined);
    setStatus(undefined);
    setIncludeInactive(false);
    setPage(1);
  };

  const openDetail = async (record: Student) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      setDetail(await fetchStudent(record.student_no));
    } catch (err) {
      message.error((err as ApiError).message || '加载学生详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const columns: ColumnsType<Student> = [
    {
      title: '学号',
      dataIndex: 'student_no',
      width: 168,
      fixed: 'left',
      render: (value: string) => <span className="mono">{value}</span>,
    },
    {
      title: '姓名',
      dataIndex: 'student_name',
      width: 100,
      render: (value: string, record) => (
        <span style={{ color: record.is_active ? 'var(--ink)' : 'var(--faint)' }}>{value}</span>
      ),
    },
    { title: '学院', dataIndex: 'college_name', width: 140, render: (v) => v ?? '—' },
    { title: '专业', dataIndex: 'major_name', width: 180, render: (v) => v ?? '—' },
    { title: '班级', dataIndex: 'class_name', width: 170, render: (v) => v ?? '—' },
    {
      title: '入学',
      dataIndex: 'enrollment_year',
      width: 72,
      align: 'right',
      render: (v) => <span className="mono cell-muted">{v ?? '—'}</span>,
    },
    {
      title: '状态',
      dataIndex: 'student_status',
      width: 92,
      render: (value: StudentStatus) => (
        <StatusBadge tone={STATUS_TONE[value]} label={STUDENT_STATUS_LABEL[value] ?? value} />
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 160,
      render: (v: string) => <span className="cell-muted mono">{formatTime(v)}</span>,
    },
    {
      title: '',
      key: 'action',
      width: 72,
      align: 'right',
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => void openDetail(record)}>
          详情
        </Button>
      ),
    },
  ];

  const changeColumns: ColumnsType<StudentChange> = [
    {
      title: '异动类型',
      dataIndex: 'change_type',
      width: 100,
      render: (v: StudentChange['change_type']) => CHANGE_TYPE_LABEL[v] ?? v,
    },
    {
      title: '生效日期',
      dataIndex: 'effective_date',
      width: 110,
      render: (v: string) => <span className="mono">{v}</span>,
    },
    {
      title: '记录状态',
      dataIndex: 'record_status',
      width: 96,
      render: (v: StudentChange['record_status']) => {
        const tone =
          v === 'confirmed' ? 'success' : v === 'returned' ? 'danger' : v === 'pending_review' ? 'warning' : 'muted';
        return <StatusBadge tone={tone} label={RECORD_STATUS_LABEL[v] ?? v} />;
      },
    },
    { title: '异动原因', dataIndex: 'change_reason', render: (v) => v ?? '—' },
  ];

  const counts = filters?.status_counts ?? {};

  return (
    <>
      <PageHeader
        title="学生信息"
        description="查询全校学生基础信息与学籍异动记录，数据来自业务库实时查询。"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        }
      />

      <div className="stat-row">
        <StatTile label="在校学生" value={filters?.total_active ?? '—'} hint="含休学等非退学状态" />
        <StatTile label="正常在校" value={counts.enrolled ?? '—'} hint="状态为 enrolled" />
        <StatTile label="休学中" value={counts.suspended ?? '—'} hint="状态为 suspended" />
        <StatTile label="异动记录" value={filters?.change_total ?? '—'} hint="全部有效异动" />
      </div>

      <Panel flush>
        <div className="filter-bar">
          <div className="field is-grow">
            <span className="field-label">关键词</span>
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: 'var(--faint)' }} />}
              aria-label="关键词（学号或姓名）"
              placeholder="输入学号或姓名"
              value={keyword}
              onChange={(e) => {
                setKeyword(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div className="field">
            <span className="field-label">学院</span>
            <Select
              aria-label="学院"
              allowClear
              placeholder="全部"
              style={{ width: 156 }}
              value={college}
              onChange={(v) => {
                setCollege(v);
                setPage(1);
              }}
              options={(filters?.colleges ?? []).map((item) => ({ label: item, value: item }))}
            />
          </div>
          <div className="field">
            <span className="field-label">班级</span>
            <Select
              aria-label="班级"
              allowClear
              showSearch
              placeholder="全部"
              style={{ width: 190 }}
              value={className}
              onChange={(v) => {
                setClassName(v);
                setPage(1);
              }}
              options={(filters?.classes ?? []).map((item) => ({ label: item, value: item }))}
            />
          </div>
          <div className="field">
            <span className="field-label">在校状态</span>
            <Select
              aria-label="在校状态"
              allowClear
              placeholder="全部"
              style={{ width: 124 }}
              value={status}
              onChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
              options={(Object.keys(STUDENT_STATUS_LABEL) as StudentStatus[]).map((key) => ({
                label: STUDENT_STATUS_LABEL[key],
                value: key,
              }))}
            />
          </div>
          <div className="field">
            <span className="field-label">停用记录</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 32 }}>
              <Switch
                aria-label="显示停用记录"
                size="small"
                checked={includeInactive}
                onChange={(checked) => {
                  setIncludeInactive(checked);
                  setPage(1);
                }}
              />
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>显示</span>
            </div>
          </div>
          <div className="filter-actions">
            <Button type="text" onClick={resetFilters}>
              重置
            </Button>
          </div>
        </div>
      </Panel>

      {error && (
        <Alert
          style={{ marginTop: 12 }}
          type="error"
          showIcon
          message="查询失败"
          description={error}
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        />
      )}

      <Panel
        title="学生列表"
        sub={`${total} 条记录`}
        flush
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            服务端分页 · 每页 {pageSize} 条
          </Typography.Text>
        }
      >
        <Table<Student>
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={loading}
          scroll={{ x: 1180 }}
          locale={{
            emptyText: error ? (
              <EmptyState title="数据加载失败" hint="请检查后端服务后重试" />
            ) : (
              <EmptyState title="没有符合条件的学生" hint="尝试调整关键词或筛选条件" />
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100],
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </Panel>

      <Drawer
        width={760}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        loading={detailLoading}
        title={
          detail ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>{detail.student_name}</span>
              <span className="mono" style={{ color: 'var(--muted)', fontWeight: 400 }}>
                {detail.student_no}
              </span>
            </span>
          ) : (
            '学生详情'
          )
        }
      >
        {detail && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="学号">
                <span className="mono">{detail.student_no}</span>
              </Descriptions.Item>
              <Descriptions.Item label="姓名">{detail.student_name}</Descriptions.Item>
              <Descriptions.Item label="学院">{detail.college_name ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="专业">{detail.major_name ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="班级">{detail.class_name ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="入学年份">
                <span className="mono">{detail.enrollment_year ?? '—'}</span>
              </Descriptions.Item>
              <Descriptions.Item label="在校状态">
                <StatusBadge
                  tone={STATUS_TONE[detail.student_status]}
                  label={STUDENT_STATUS_LABEL[detail.student_status]}
                />
              </Descriptions.Item>
              <Descriptions.Item label="记录状态">
                {detail.is_active ? '有效' : '已停用'}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间" span={2}>
                <span className="mono cell-muted">{formatTime(detail.updated_at)}</span>
              </Descriptions.Item>
            </Descriptions>

            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  marginBottom: 10,
                }}
              >
                <span style={{ fontSize: 13.5, fontWeight: 600 }}>学籍异动</span>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                  共 {detail.change_total} 条，显示最近 {detail.changes.length} 条
                </span>
              </div>
              <Table<StudentChange>
                rowKey="id"
                size="small"
                columns={changeColumns}
                dataSource={detail.changes}
                pagination={false}
                scroll={{ x: 620 }}
                locale={{ emptyText: <Empty description="暂无学籍异动记录" /> }}
              />
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}
