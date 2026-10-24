import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
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
import type { DemoStudent } from '../demo/types';
import { useDemoData } from '../demo/useDemoData';
import { downloadFourSheet } from '../demo/download';

type FieldKey =
  | 'uid'
  | 'name'
  | 'gender'
  | 'college'
  | 'major'
  | 'class_name'
  | 'grade'
  | 'enrollment_year'
  | 'status'
  | 'counselor'
  | 'phone'
  | 'id_card'
  | 'source_region'
  | 'change_count'
  | 'flags';

interface FieldDef {
  key: FieldKey;
  label: string;
  group: string;
  sensitive?: boolean;
  get: (student: DemoStudent) => string;
}

interface ReportTemplate {
  id: string;
  name: string;
  description: string;
  fields: FieldKey[];
  flag?: string;
  status?: string;
}

interface ExportLog {
  id: string;
  time: string;
  report: string;
  rows: number;
  fields: number;
}

const FIELDS: FieldDef[] = [
  { key: 'uid', label: 'UID', group: '基础', get: (s) => s.uid },
  { key: 'name', label: '姓名（掩码）', group: '基础', sensitive: true, get: (s) => s.name },
  { key: 'gender', label: '性别', group: '基础', get: (s) => s.gender },
  { key: 'college', label: '二级学院', group: '组织', get: (s) => s.college },
  { key: 'major', label: '专业', group: '组织', get: (s) => s.major },
  { key: 'class_name', label: '班级', group: '组织', get: (s) => s.class_name },
  { key: 'grade', label: '年级', group: '组织', get: (s) => s.grade },
  { key: 'enrollment_year', label: '入学年份', group: '组织', get: (s) => (s.enrollment_year ? String(s.enrollment_year) : '—') },
  { key: 'status', label: '学籍状态', group: '学籍', get: (s) => s.status },
  { key: 'counselor', label: '辅导员', group: '学籍', get: (s) => s.counselor },
  { key: 'change_count', label: '异动次数', group: '学籍', get: (s) => String(s.change_count) },
  { key: 'phone', label: '本人电话（掩码）', group: '联系方式', sensitive: true, get: (s) => s.phone },
  { key: 'id_card', label: '身份证（掩码）', group: '联系方式', sensitive: true, get: (s) => s.id_card },
  { key: 'source_region', label: '生源地', group: '联系方式', get: (s) => s.source_region },
  { key: 'flags', label: '数据标记', group: '数据质量', get: (s) => (s.flags.length ? s.flags.join('、') : '无') },
];

const FIELD_MAP = new Map(FIELDS.map((field) => [field.key, field]));

const TEMPLATES: ReportTemplate[] = [
  {
    id: 'insurance',
    name: '学平险名单',
    description: '按学院/班级导出投保所需字段，手机号与身份证默认掩码。',
    fields: ['uid', 'name', 'gender', 'college', 'major', 'class_name', 'id_card', 'phone'],
  },
  {
    id: 'roster',
    name: '班级花名册',
    description: '辅导员带班、学生状态与组织归属，适合打印或发班级。',
    fields: ['uid', 'name', 'gender', 'college', 'major', 'class_name', 'status', 'counselor'],
  },
  {
    id: 'changes',
    name: '学籍异动名单',
    description: '只筛有异动的学生，含异动次数；明细可在工作台查看。',
    fields: ['uid', 'name', 'college', 'class_name', 'status', 'change_count'],
    flag: 'has_change',
  },
  {
    id: 'withdrawn',
    name: '退学名单',
    description: '按学籍状态筛选退学学生；不导出身份证、电话。',
    fields: ['uid', 'name', 'gender', 'college', 'major', 'class_name', 'status'],
    status: '退学',
  },
  {
    id: 'quality',
    name: '数据质量清单',
    description: '导出有缺字段、身份证异常、班级未匹配等标记的学生。',
    fields: ['uid', 'name', 'college', 'class_name', 'flags'],
    flag: 'quality',
  },
];

const DEFAULT_FIELDS: FieldKey[] = TEMPLATES[1].fields;
const LOG_KEY = 'campus.demo.reportLogs.v1';

function loadLogs(): ExportLog[] {
  try {
    const raw = window.localStorage.getItem(LOG_KEY);
    return raw ? (JSON.parse(raw) as ExportLog[]) : [];
  } catch {
    return [];
  }
}

function toCsv(rows: DemoStudent[], fields: FieldDef[]): string {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const header = fields.map((field) => escape(field.label)).join(',');
  const body = rows.map((student) => fields.map((field) => escape(field.get(student))).join(','));
  return `\uFEFF${[header, ...body].join('\r\n')}`;
}

export default function ReportsPage() {
  const { data, error } = useDemoData();
  const [selectedKeys, setSelectedKeys] = useState<FieldKey[]>(DEFAULT_FIELDS);
  const [activeTemplate, setActiveTemplate] = useState('roster');
  const [keyword, setKeyword] = useState('');
  const [college, setCollege] = useState('all');
  const [status, setStatus] = useState('all');
  const [className, setClassName] = useState('all');
  const [flag, setFlag] = useState('all');
  const [logs, setLogs] = useState<ExportLog[]>(loadLogs);

  useEffect(() => {
    setLogs(loadLogs());
  }, []);

  const selectedFields = useMemo(
    () => selectedKeys.map((key) => FIELD_MAP.get(key)).filter((field): field is FieldDef => Boolean(field)),
    [selectedKeys],
  );

  const colleges = data?.metrics.college_counts.map((item) => item.name) ?? [];
  const statuses = data?.metrics.status_counts.map((item) => item.name) ?? [];
  const classOptions = data?.class_summary.map((item) => item.class_name) ?? [];

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = keyword.trim().toLowerCase();
    return data.students.filter((student) => {
      if (college !== 'all' && student.college !== college) return false;
      if (status !== 'all' && student.status !== status) return false;
      if (className !== 'all' && student.class_name !== className) return false;
      if (flag === 'has_change' && student.change_count === 0) return false;
      if (flag === 'quality' && student.flags.length === 0) return false;
      if (q) {
        const haystack = `${student.uid} ${student.class_name} ${student.major} ${student.counselor}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [data, keyword, college, status, className, flag]);

  const preview = useMemo(
    () =>
      filtered.slice(0, 20).map((student) => ({
        key: student.uid,
        ...Object.fromEntries(selectedFields.map((field) => [field.key, field.get(student)])),
      })),
    [filtered, selectedFields],
  );

  const columns: ColumnsType<Record<string, string>> = selectedFields.map((field) => ({
    title: field.label,
    dataIndex: field.key,
    key: field.key,
    width: field.key === 'uid' ? 150 : field.key === 'flags' ? 220 : 130,
    ellipsis: true,
  }));

  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="演示数据加载失败"
        description={`${error}。请确认 demo-api 服务与网关可用。`}
      />
    );
  }

  if (!data) {
    return (
      <div className="wb wb-loading">
        <Spin size="large" />
        <span>正在加载本地演示数据…</span>
      </div>
    );
  }

  const applyTemplate = (template: ReportTemplate) => {
    setActiveTemplate(template.id);
    setSelectedKeys(template.fields);
    setCollege('all');
    setStatus(template.status ?? 'all');
    setClassName('all');
    setKeyword('');
    setFlag(template.flag ?? 'all');
  };

  const toggleField = (key: FieldKey, checked: boolean) => {
    setActiveTemplate('custom');
    setSelectedKeys((current) => (checked ? [...new Set([...current, key])] : current.filter((item) => item !== key)));
  };

  const reset = () => {
    setActiveTemplate('roster');
    setSelectedKeys(TEMPLATES[1].fields);
    setKeyword('');
    setCollege('all');
    setStatus('all');
    setClassName('all');
    setFlag('all');
  };

  const onExport = () => {
    if (!selectedFields.length) {
      void message.warning('至少选择一个导出字段');
      return;
    }
    if (!filtered.length) {
      void message.warning('当前筛选没有命中学生');
      return;
    }
    const template = TEMPLATES.find((item) => item.id === activeTemplate);
    const csv = toCsv(filtered, selectedFields);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${template?.name ?? '自定义报表'}_${todayStamp()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    const next: ExportLog[] = [
      {
        id: `${Date.now()}`,
        time: new Date().toLocaleString('zh-CN', { hour12: false }),
        report: template?.name ?? '自定义报表',
        rows: filtered.length,
        fields: selectedFields.length,
      },
      ...logs,
    ].slice(0, 8);
    setLogs(next);
    window.localStorage.setItem(LOG_KEY, JSON.stringify(next));
    void message.success(`已导出 ${fmt(filtered.length)} 行 × ${selectedFields.length} 列`);
  };

  const selectedSensitive = selectedFields.filter((field) => field.sensitive).length;

  return (
    <div className="wb">
      <PageHeader
        title="报表中心"
        description="同一份学生主档，按部门需求勾选字段、筛选范围、导出标准表格。敏感字段默认掩码，导出留痕。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">LOCAL ONLY</span>
            <span className="wb-badge is-demo">演示数据 · 非真实人员信息</span>
          </div>
        }
      />

      <div className="rp-templates">
        {TEMPLATES.map((template) => (
          <button
            type="button"
            key={template.id}
            className={`rp-template${activeTemplate === template.id ? ' is-active' : ''}`}
            onClick={() => applyTemplate(template)}
          >
            <b>{template.name}</b>
            <span>{template.description}</span>
          </button>
        ))}
      </div>

      <div className="wb-grid rp-main">
        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>选择字段</h2>
            <span>{selectedFields.length} 列 · 敏感字段 {selectedSensitive} 个</span>
          </header>
          <div className="rp-field-groups">
            {['基础', '组织', '学籍', '联系方式', '数据质量'].map((group) => (
              <div className="rp-field-group" key={group}>
                <div className="rp-field-group-title">{group}</div>
                <div className="rp-field-grid">
                  {FIELDS.filter((field) => field.group === group).map((field) => (
                    <Checkbox
                      key={field.key}
                      checked={selectedKeys.includes(field.key)}
                      onChange={(event) => toggleField(field.key, event.target.checked)}
                    >
                      <span className={field.sensitive ? 'rp-sensitive' : undefined}>
                        {field.label}
                        {field.sensitive ? <Tag color="orange">掩码</Tag> : null}
                      </span>
                    </Checkbox>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="rp-field-actions">
            <Button size="small" onClick={() => setSelectedKeys(FIELDS.map((field) => field.key))}>
              全选
            </Button>
            <Button size="small" onClick={() => setSelectedKeys([])}>
              清空
            </Button>
            <Button size="small" onClick={reset}>恢复花名册模板</Button>
          </div>
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>筛选范围</h2>
            <span>本地数据 · 实时预览</span>
          </header>
          <div className="rp-filter-grid">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              aria-label="搜索学生"
              placeholder="UID / 班级 / 专业 / 辅导员"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              aria-label="学院"
              value={college}
              onChange={setCollege}
              options={[{ value: 'all', label: '全部学院' }, ...colleges.map((item) => ({ value: item, label: item }))]}
            />
            <Select
              aria-label="学籍状态"
              value={status}
              onChange={setStatus}
              options={[{ value: 'all', label: '全部学籍状态' }, ...statuses.map((item) => ({ value: item, label: item }))]}
            />
            <Select
              aria-label="班级"
              showSearch
              value={className}
              onChange={setClassName}
              optionFilterProp="label"
              options={[{ value: 'all', label: '全部班级' }, ...classOptions.map((item) => ({ value: item, label: item }))]}
            />
            <Select
              aria-label="学生类型"
              value={flag}
              onChange={setFlag}
              options={[
                { value: 'all', label: '全部学生' },
                { value: 'has_change', label: '有学籍异动' },
                { value: 'quality', label: '有数据标记' },
              ]}
            />
            <Button onClick={reset}>重置</Button>
          </div>
          <div className="rp-summary">
            <div><span>命中学生</span><b>{fmt(filtered.length)}</b></div>
            <div><span>导出字段</span><b>{selectedFields.length}</b></div>
            <div><span>敏感字段</span><b>{selectedSensitive}</b></div>
          </div>
          <div className="rp-export">
            <Button type="primary" icon={<DownloadOutlined />} onClick={onExport}>
              导出 CSV（Excel 可打开）
            </Button>
            <button type="button" className="wb-download" onClick={() => void downloadFourSheet()}>
              下载四件套 Excel
            </button>
          </div>
          <p className="wb-note">
            演示版在浏览器本地生成文件，不上传服务器；正式版将由后端生成并记录操作人、时间、字段与行数。身份证与电话已掩码，导出仍建议按最小必要字段。
          </p>
        </section>
      </div>

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head">
          <h2>导出预览</h2>
          <span>前 20 行 · 共 {fmt(filtered.length)} 行 · {selectedFields.length} 列</span>
        </header>
        {selectedFields.length ? (
          <Table<Record<string, string>>
            rowKey="key"
            size="middle"
            columns={columns}
            dataSource={preview}
            pagination={false}
            scroll={{ x: Math.max(800, selectedFields.length * 140) }}
            locale={{ emptyText: <Empty description="没有匹配的学生" /> }}
          />
        ) : (
          <Empty description="请选择至少一个字段" />
        )}
      </section>

      <div className="wb-grid wb-grid-bottom">
        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>导出记录</h2>
            <span>本机浏览器 · 最近 8 次</span>
          </header>
          {logs.length ? (
            <div className="rp-log-list">
              {logs.map((log) => (
                <div className="rp-log" key={log.id}>
                  <span>{log.time}</span>
                  <b>{log.report}</b>
                  <small>{fmt(log.rows)} 行 · {log.fields} 列</small>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="还没有导出记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
          <p className="wb-note">正式版会把导出记录写入服务端审计表，而不是浏览器本地。</p>
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>导出边界</h2>
            <span>最小必要 · 脱敏 · 留痕</span>
          </header>
          <ul className="wb-uid-list">
            <li>所有学生记录已生成 UID；导出不包含原始学号。</li>
            <li>姓名、身份证、电话默认掩码；需要完整值时走单独授权。</li>
            <li>学生自助、辅导员、教务、学工均按角色限制字段与范围。</li>
            <li>导出文件可加水印/页脚“演示数据，非真实人员信息”。</li>
          </ul>
          <div className="wb-source">
            数据源：{data.metrics.source_files.map((item) => `${item.name}（${fmt(item.rows)} 行）`).join('；')}
          </div>
        </section>
      </div>

      <p className="wb-footnote">{data.metrics.disclaimer} · 报表中心 · 本地演示版</p>
    </div>
  );
}
