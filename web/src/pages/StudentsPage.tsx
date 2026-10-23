import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Table,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { ApiError } from '../api/client';
import {
  exportStudents,
  fetchFilterOptions,
  fetchStudent,
  fetchStudentAudit,
  fetchStudents,
  updateStudent,
  type StudentEditableFields,
} from '../api/students';
import type {
  FilterOptions,
  Student,
  StudentAuditLog,
  StudentChange,
  StudentDetail,
  StudentStatus,
} from '../api/types';
import { EXPORT_FIELD_OPTIONS } from '../api/types';
import { CHANGE_TYPE_LABEL, RECORD_STATUS_LABEL, STUDENT_STATUS_LABEL } from '../api/types';
import { EmptyState, PageHeader, Panel, StatTile, StatusBadge } from '../components/ui';

const STATUS_TONE: Record<StudentStatus, 'success' | 'warning' | 'danger' | 'info' | 'muted'> = {
  enrolled: 'success',
  suspended: 'warning',
  withdrawn: 'danger',
  graduated: 'info',
  other: 'muted',
};

const ACTION_LABEL: Record<StudentAuditLog['action'], string> = {
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

export default function StudentsPage() {
  const [searchParams] = useSearchParams();
  const [keyword, setKeyword] = useState(searchParams.get('keyword') ?? '');
  const [debouncedKeyword, setDebouncedKeyword] = useState(searchParams.get('keyword') ?? '');
  const [college, setCollege] = useState<string | undefined>(searchParams.get('college') ?? undefined);
  const [className, setClassName] = useState<string | undefined>(searchParams.get('class_name') ?? undefined);
  const [status, setStatus] = useState<string | undefined>(searchParams.get('status') ?? undefined);
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
  const [audit, setAudit] = useState<StudentAuditLog[]>([]);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<StudentEditableFields>();

  const [exportOpen, setExportOpen] = useState(false);
  const [exportFields, setExportFields] = useState<string[]>(
    EXPORT_FIELD_OPTIONS.map((f) => f.value),
  );
  const [exportSplit, setExportSplit] = useState(false);

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
    setEditing(false);
    setDetailLoading(true);
    setDetail(null);
    setAudit([]);
    try {
      const [detailData, auditData] = await Promise.all([
        fetchStudent(record.student_no),
        fetchStudentAudit(record.student_no),
      ]);
      setDetail(detailData);
      setAudit(auditData.items);
    } catch (err) {
      message.error((err as ApiError).message || '加载学生详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const startEdit = () => {
    if (!detail) return;
    form.setFieldsValue({
      student_name: detail.student_name,
      class_name: detail.class_name ?? undefined,
      major_name: detail.major_name ?? undefined,
      enrollment_year: detail.enrollment_year ?? undefined,
      student_status: detail.student_status,
    });
    setEditing(true);
  };

  const cancelEdit = () => setEditing(false);

  const handleSave = async () => {
    if (!detail) return;
    let values: StudentEditableFields;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const changed: Partial<StudentEditableFields> = {};
    Object.entries(values).forEach(([k, v]) => {
      if (form.isFieldTouched(k as keyof StudentEditableFields)) {
        (changed as Record<string, unknown>)[k] = v === '' ? null : v;
      }
    });
    if (Object.keys(changed).length === 0) {
      message.info('没有字段被修改');
      return;
    }
    setSaving(true);
    try {
      await updateStudent(detail.student_no, changed);
      message.success('已保存修改，操作已留痕');
      setEditing(false);
      const [detailData, auditData] = await Promise.all([
        fetchStudent(detail.student_no),
        fetchStudentAudit(detail.student_no),
      ]);
      setDetail(detailData);
      setAudit(auditData.items);
      void load();
    } catch (err) {
      message.error((err as ApiError).message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleExport = () => {
    if (exportFields.length === 0) {
      message.warning('请至少选择一个导出字段');
      return;
    }
    setExportOpen(false);
    exportStudents(
      {
        keyword: debouncedKeyword || undefined,
        college,
        class_name: className,
        status,
        include_inactive: includeInactive,
      },
      exportFields,
      exportSplit,
    );
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
      render: (value: string, record: Student) => (
        <span style={{ color: record.is_active ? 'var(--ink)' : 'var(--faint)' }}>{value}</span>
      ),
    },
    { title: '学院', dataIndex: 'college_name', width: 140, render: (v: string | null) => v ?? '—' },
    { title: '专业', dataIndex: 'major_name', width: 180, render: (v: string | null) => v ?? '—' },
    { title: '班级', dataIndex: 'class_name', width: 170, render: (v: string | null) => v ?? '—' },
    {
      title: '入学',
      dataIndex: 'enrollment_year',
      width: 72,
      align: 'right',
      render: (v: number | null) => <span className="mono cell-muted">{v ?? '—'}</span>,
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
      render: (_: unknown, record: Student) => (
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
    { title: '异动原因', dataIndex: 'change_reason', render: (v: string | null) => v ?? '—' },
  ];

  const auditColumns: ColumnsType<StudentAuditLog> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => <span className="cell-muted mono">{formatTime(v)}</span>,
    },
    {
      title: '操作人',
      dataIndex: 'actor_user_id',
      width: 140,
      render: (v: string | null, record: StudentAuditLog) => <span className="mono">{v || record.actor_db_role}</span>,
    },
    {
      title: '动作',
      dataIndex: 'action',
      width: 72,
      render: (v: StudentAuditLog['action']) => ACTION_LABEL[v] ?? v,
    },
    {
      title: '变更字段',
      dataIndex: 'changed_fields',
      width: 160,
      render: (v: string[] | null) => (v && v.length ? v.join('、') : '—'),
    },
    {
      title: '变更明细（修改前 → 修改后）',
      key: 'detail',
      render: (_: unknown, record: StudentAuditLog) => {
        const fields = record.changed_fields ?? [];
        if (!fields.length) return '—';
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {fields.map((f: string) => (
              <div key={f} style={{ fontSize: 12 }}>
                <span className="mono" style={{ color: 'var(--muted)' }}>{f}</span>：{' '}
                <span className="cell-muted mono">{fmtVal(record.before_data?.[f])}</span>
                {' → '}
                <span className="mono">{fmtVal(record.after_data?.[f])}</span>
              </div>
            ))}
          </div>
        );
      },
    },
  ];

  const counts = filters?.status_counts ?? {};

  return (
    <>
      <PageHeader
        title="学生信息"
        description="查询全校学生基础信息与学籍异动记录，数据来自业务库实时查询；支持单条编辑，每次修改自动留痕。"
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
          <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              服务端分页 · 每页 {pageSize} 条
            </Typography.Text>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => setExportOpen(true)}
              disabled={total === 0}
            >
              导出 Excel
            </Button>
          </span>
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
        width={780}
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
        extra={
          detail &&
          (editing ? (
            <span style={{ display: 'flex', gap: 8 }}>
              <Button onClick={cancelEdit} disabled={saving}>
                取消
              </Button>
              <Button type="primary" onClick={() => void handleSave()} loading={saving}>
                保存
              </Button>
            </span>
          ) : (
            <Button type="primary" onClick={startEdit}>
              编辑
            </Button>
          ))
        }
      >
        {detail && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {editing ? (
              <Form<StudentEditableFields> form={form} layout="vertical" requiredMark>
                <Form.Item
                  label="姓名"
                  name="student_name"
                  rules={[{ required: true, message: '姓名不能为空' }]}
                >
                  <Input placeholder="请输入姓名" />
                </Form.Item>
                <Form.Item label="班级" name="class_name">
                  <Input placeholder="清空则置空" />
                </Form.Item>
                <Form.Item label="专业" name="major_name">
                  <Input placeholder="清空则置空" />
                </Form.Item>
                <Form.Item label="入学年份" name="enrollment_year">
                  <InputNumber style={{ width: '100%' }} min={1990} max={2100} placeholder="如 2024" />
                </Form.Item>
                <Form.Item label="在校状态" name="student_status">
                  <Select
                    options={(Object.keys(STUDENT_STATUS_LABEL) as StudentStatus[]).map((key) => ({
                      label: STUDENT_STATUS_LABEL[key],
                      value: key,
                    }))}
                  />
                </Form.Item>
              </Form>
            ) : (
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
            )}

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

            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  marginBottom: 10,
                }}
              >
                <span style={{ fontSize: 13.5, fontWeight: 600 }}>操作记录（编辑留痕）</span>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                  共 {audit.length} 条（最近 {audit.length} 条）
                </span>
              </div>
              <Table<StudentAuditLog>
                rowKey="id"
                size="small"
                columns={auditColumns}
                dataSource={audit}
                pagination={false}
                scroll={{ x: 720 }}
                locale={{ emptyText: <Empty description="暂无编辑记录" /> }}
              />
            </div>
          </div>
        )}
      </Drawer>

      <Drawer
        title="导出 Excel"
        width={420}
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        extra={
          <span style={{ display: 'flex', gap: 8 }}>
            <Button onClick={() => setExportOpen(false)}>取消</Button>
            <Button type="primary" onClick={handleExport}>
              导出
            </Button>
          </span>
        }
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          导出范围与当前筛选条件一致（共 {total} 条）。勾选需要的字段，按统一格式生成 Excel。
        </Typography.Paragraph>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
          {EXPORT_FIELD_OPTIONS.map((opt) => (
            <Checkbox
              key={opt.value}
              checked={exportFields.includes(opt.value)}
              onChange={(e) => {
                setExportFields((prev) =>
                  e.target.checked
                    ? [...prev, opt.value]
                    : prev.filter((v) => v !== opt.value),
                );
              }}
            >
              {opt.label}
            </Checkbox>
          ))}
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: 16,
            paddingTop: 14,
            borderTop: '1px solid var(--line)',
          }}
        >
          <div>
            <div style={{ fontWeight: 600 }}>每学院一个工作表</div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              开启后按学院拆分下载，便于分部门下发
            </Typography.Text>
          </div>
          <Switch checked={exportSplit} onChange={setExportSplit} />
        </div>
      </Drawer>
    </>
  );
}
