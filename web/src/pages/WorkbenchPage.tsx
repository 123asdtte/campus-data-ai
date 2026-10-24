import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
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
import { SearchOutlined } from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageHeader } from '../components/ui';
import StudentProfileDrawer from '../components/StudentProfileDrawer';

import { fmt } from '../demo/format';
import type { DemoStudent, NameCount, QualityItem, Tone } from '../demo/types';
import { useDemoData } from '../demo/useDemoData';
import { downloadFourSheet } from '../demo/download';

const TONE_COLOR: Record<Tone, string> = {
  success: 'green',
  info: 'blue',
  warning: 'orange',
  danger: 'red',
  muted: 'default',
};

const QUALITY_KEYS = ['duplicate_rows', 'same_name_groups', 'id_invalid', 'class_not_found', 'transfer_conflicts'];

function exampleLabel(ex: Record<string, unknown>): string {
  const parts = [ex.uid, ex.name, ex.class_name, ex.change_no].filter(Boolean).map(String);
  if (ex.from_major) {
    parts.push(`${String(ex.from_major)} → ${String(ex.to ?? '')}`);
  }
  return parts.join(' · ');
}

function BarList({
  items,
  color,
  empty = '暂无数据',
}: {
  items: NameCount[];
  color?: string;
  empty?: string;
}) {
  const max = Math.max(1, ...items.map((item) => item.count));
  if (!items.length) return <div className="wb-empty">{empty}</div>;
  return (
    <div className="wb-chart-list">
      {items.map((item) => (
        <div className="wb-chart-row" key={item.name}>
          <span className="wb-chart-label" title={item.name}>
            {item.name || '未填'}
          </span>
          <span className="wb-chart-track">
            <span
              className="wb-chart-fill"
              style={{ width: `${Math.max(2, (item.count / max) * 100)}%`, background: color }}
            />
          </span>
          <span className="wb-chart-value">{fmt(item.count)}</span>
        </div>
      ))}
    </div>
  );
}

function QualityCard({ item, tone }: { item: QualityItem; tone: 'warning' | 'info' | 'danger' }) {
  return (
    <div className={`wb-quality-item is-${tone}`}>
      <div className="wb-quality-top">
        <span>{item.label}</span>
        <b>{fmt(item.count)}</b>
      </div>
      <p>{item.description}</p>
      {item.examples && item.examples.length > 0 ? (
        <div className="wb-quality-examples">
          {item.examples.slice(0, 3).map((ex, index) => (
            <span key={`${item.label}-${index}`}>{exampleLabel(ex)}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function WorkbenchPage() {
  const { data, error } = useDemoData();
  const [keyword, setKeyword] = useState('');
  const [college, setCollege] = useState('all');
  const [status, setStatus] = useState('all');
  const [flag, setFlag] = useState('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState<DemoStudent | null>(null);

  useEffect(() => {
    setPage(1);
  }, [keyword, college, status, flag]);

  const colleges = data?.metrics.college_counts.map((item) => item.name) ?? [];
  const statuses = data?.metrics.status_counts.map((item) => item.name) ?? [];

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = keyword.trim().toLowerCase();
    return data.students.filter((student) => {
      if (college !== 'all' && student.college !== college) return false;
      if (status !== 'all' && student.status !== status) return false;
      if (flag === 'has_change' && student.change_count === 0) return false;
      if (flag === 'missing' && !student.flags.some((item) => item.includes('缺'))) return false;
      if (flag === 'quality' && student.flags.length === 0) return false;
      if (q) {
        const haystack = `${student.uid} ${student.class_name} ${student.class_short} ${student.major} ${student.counselor}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [data, keyword, college, status, flag]);

  const paged = useMemo(
    () => filtered.slice((page - 1) * pageSize, page * pageSize),
    [filtered, page, pageSize],
  );

  const selectedChanges = useMemo(
    () => (selected && data ? data.changes.filter((item) => item.uid === selected.uid) : []),
    [data, selected],
  );

  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const focusUid = params.get('student') ?? '';
  const warnedFocus = useRef('');

  useEffect(() => {
    if (!data || !focusUid) return;
    const student = data.students.find((item) => item.uid === focusUid);
    if (student) {
      setSelected(student);
      return;
    }
    setSelected(null);
    if (warnedFocus.current !== focusUid) {
      warnedFocus.current = focusUid;
      message.warning('该学生不在当前账号的数据范围，未打开档案');
    }
  }, [data, focusUid]);

  const closeStudent = () => {
    setSelected(null);
    if (focusUid) {
      const next = new URLSearchParams(params);
      next.delete('student');
      setParams(next, { replace: true });
    }
  };

  const openStudent = (student: DemoStudent) => {
    setSelected(student);
    setParams({ student: student.uid }, { replace: true });
  };

  if (error) {
    return (
      <div className="wb">
        <Alert
          type="error"
          showIcon
          message="演示数据加载失败"
          description={`${error}。请确认 demo-api 服务与网关可用，并重新加载页面。`}
        />
      </div>
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

  const metrics = data.metrics;
  const active = metrics.status_counts.find((item) => item.name === '在籍')?.count ?? 0;
  const qualityCount = QUALITY_KEYS.reduce((sum, key) => sum + (metrics.data_quality[key]?.count ?? 0), 0);
  const sameNameAll = metrics.data_quality.same_name_all?.count ?? 0;
  const classMissing = metrics.data_quality.class_not_found;
  const approved = metrics.change_status_counts.find((item) => item.name === '已批')?.count ?? 0;
  const pending = metrics.change_status_counts.find((item) => item.name === '审批中')?.count ?? 0;

  const columns: ColumnsType<DemoStudent> = [
    {
      title: 'UID',
      dataIndex: 'uid',
      width: 148,
      render: (value: string) => <span className="wb-mono">{value}</span>,
    },
    {
      title: '学生',
      dataIndex: 'name',
      width: 92,
      render: (value: string, row) => (
        <span>
          {value}
          <span className="wb-gender">{row.gender}</span>
        </span>
      ),
    },
    {
      title: '学院 / 专业',
      dataIndex: 'college',
      width: 210,
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{value}</b>
          <small>{row.major}</small>
        </span>
      ),
    },
    {
      title: '班级',
      dataIndex: 'class_short',
      width: 150,
      render: (value: string, row) => (
        <span className="wb-two-line">
          <b>{value || row.class_name}</b>
          <small>{row.counselor === '—' ? '未匹配辅导员' : row.counselor}</small>
        </span>
      ),
    },
    {
      title: '学籍状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string, row) => <Tag color={TONE_COLOR[row.status_tone]}>{value}</Tag>,
    },
    {
      title: '联系方式',
      dataIndex: 'phone',
      width: 124,
      render: (value: string) => <span className="wb-mono">{value}</span>,
    },
    {
      title: '标记',
      dataIndex: 'flags',
      width: 220,
      render: (values: string[]) =>
        values.length ? (
          <span className="wb-flags">
            {values.slice(0, 3).map((item) => (
              <span className="wb-flag" key={item}>
                {item}
              </span>
            ))}
            {values.length > 3 ? <span className="wb-flag">+{values.length - 3}</span> : null}
          </span>
        ) : (
          <span className="wb-muted">—</span>
        ),
    },
  ];

  return (
    <div className="wb">
      <PageHeader
        title="数据工作台"
        description="把学校多张来源表整理成一份可核对、可导出、可追溯的学生数据。当前为本地演示，全部使用虚构数据。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">LOCAL ONLY</span>
            <span className="wb-badge is-demo">演示数据 · 非真实人员信息</span>
          </div>
        }
      />

      <div className="wb-flow">
        <span className="wb-flow-label">WORKBUDDY → LOCAL</span>
        <span>收件箱</span><i>→</i><span>识别 / 映射 / 清洗</span><i>→</i><span>与底账核对</span><i>→</i><span>四件套 / 台账</span><i>→</i><b>UID / 脱敏 / 报表</b>
      </div>

      <section className="wb-kpis">
        <div className="wb-kpi">
          <div className="wb-kpi-label">学生总数</div>
          <div className="wb-kpi-value">{fmt(metrics.total_students)}</div>
          <div className="wb-kpi-hint">在籍 {fmt(active)} · 去重后</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">班级</div>
          <div className="wb-kpi-value">{fmt(metrics.total_classes)}</div>
          <div className="wb-kpi-hint">花名册 {metrics.roster_class_names} 个班名 · {classMissing?.count ?? 0} 人未匹配</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">学院 / 专业</div>
          <div className="wb-kpi-value">{metrics.total_colleges} <em>/</em> {metrics.total_majors}</div>
          <div className="wb-kpi-hint">{metrics.total_counselors} 位辅导员</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">学籍异动</div>
          <div className="wb-kpi-value">{fmt(metrics.change_total)}</div>
          <div className="wb-kpi-hint">已批 {approved} · 审批中 {pending}</div>
        </div>
        <div className="wb-kpi is-warn">
          <div className="wb-kpi-label">需核对项</div>
          <div className="wb-kpi-value">{fmt(qualityCount)}</div>
          <div className="wb-kpi-hint">另有 {fmt(sameNameAll)} 条同名提示</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">UID 覆盖</div>
          <div className="wb-kpi-value">100<em>%</em></div>
          <div className="wb-kpi-hint">与原始学号解耦</div>
        </div>
      </section>

      <div className="wb-grid">
        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>学院分布</h2>
            <span>按去重后人数</span>
          </header>
          <BarList items={metrics.college_counts} />
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>学籍状态</h2>
            <span>在籍 / 跟读 / 预科 / 休学 / 退学</span>
          </header>
          <div className="wb-status-list">
            {metrics.status_counts.map((item) => (
              <div className="wb-status-row" key={item.name}>
                <span className={`wb-status-dot is-${item.tone ?? 'muted'}`} />
                <span>{item.name}</span>
                <b>{fmt(item.count)}</b>
                <small>{((item.count / metrics.total_students) * 100).toFixed(1)}%</small>
              </div>
            ))}
          </div>
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>异动类型</h2>
            <span>共 {metrics.change_total} 条</span>
          </header>
          <BarList items={metrics.change_type_counts} color="var(--warning)" />
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>数据质量</h2>
            <span>先核对，再使用</span>
          </header>
          <div className="wb-quality-grid">
            {data.anomalies
              .filter((item) => item.label.includes('重复') || item.label.includes('同班') || item.label.includes('身份证') || item.label.includes('班级') || item.label.includes('转专业'))
              .map((item) => (
                <QualityCard
                  key={item.label}
                  item={item}
                  tone={item.label.includes('身份证') || item.label.includes('转专业') ? 'danger' : 'warning'}
                />
              ))}
          </div>
          <div className="wb-quality-foot">
            <span>同名同姓全库提示：{fmt(sameNameAll)} 组，不按姓名匹配</span>
            <span>招生差异：{fmt(metrics.data_quality.admissions?.count ?? 0)} 条口径差异</span>
          </div>
        </section>
      </div>

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head">
          <h2>学生主档</h2>
          <span>UID + 脱敏字段 · 点击行查看档案与异动</span>
        </header>
        <div className="wb-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            aria-label="搜索学生"
            placeholder="UID / 班级 / 专业 / 辅导员"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            style={{ width: 240 }}
          />
          <Select
            aria-label="学院"
            value={college}
            onChange={setCollege}
            style={{ width: 180 }}
            options={[{ value: 'all', label: '全部学院' }, ...colleges.map((item) => ({ value: item, label: item }))]}
          />
          <Select
            aria-label="学籍状态"
            value={status}
            onChange={setStatus}
            style={{ width: 140 }}
            options={[{ value: 'all', label: '全部状态' }, ...statuses.map((item) => ({ value: item, label: item }))]}
          />
          <Select
            aria-label="学生类型"
            value={flag}
            onChange={setFlag}
            style={{ width: 160 }}
            options={[
              { value: 'all', label: '全部学生' },
              { value: 'has_change', label: '有学籍异动' },
              { value: 'missing', label: '有缺失字段' },
              { value: 'quality', label: '有数据标记' },
            ]}
          />
          <Button
            onClick={() => {
              setKeyword('');
              setCollege('all');
              setStatus('all');
              setFlag('all');
            }}
          >
            重置
          </Button>
          <span className="wb-result-count">命中 {fmt(filtered.length)} 人</span>
        </div>
        <Table<DemoStudent>
          rowKey="uid"
          size="middle"
          columns={columns}
          dataSource={paged}
          loading={false}
          scroll={{ x: 1100 }}
          pagination={{
            current: page,
            pageSize,
            total: filtered.length,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100],
            showTotal: (total) => `共 ${fmt(total)} 人`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
          onRow={(record) => ({ onClick: () => openStudent(record) })}
          rowClassName={() => 'wb-row'}
          locale={{ emptyText: <Empty description="没有匹配的学生" /> }}
        />
      </section>

      <div className="wb-grid wb-grid-bottom">
        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>处理产物 · 四件套</h2>
            <span>WorkBuddy 同一套规则</span>
          </header>
          <div className="wb-sheet-grid">
            {[
              ['01', '标准化数据', `${fmt(metrics.total_students)} 行，UID + 脱敏字段，字段与模板一致`],
              ['02', '异常清单', `${fmt(qualityCount)} 项需核对；同名、身份证、班级、转专业逐条列出`],
              ['03', '字段映射', '原始字段 → 标准字段 → 处理理由 → 是否待确认'],
              ['04', '核对汇总', '输入 / 去重 / 匹配 / 异常计数 + 口径说明'],
            ].map(([no, title, desc]) => (
              <div className="wb-sheet" key={no}>
                <span className="wb-sheet-no">{no}</span>
                <b>{title}</b>
                <p>{desc}</p>
              </div>
            ))}
          </div>
          <button type="button" className="wb-download" onClick={() => void downloadFourSheet()}>
            下载四件套 Excel <span>↓</span>
          </button>
          <p className="wb-note">
            产物仅供演示与人工复核，不用于评奖、处分、注册或上报。原始文件不覆盖，所有输出为新文件。
          </p>
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head">
            <h2>UID 与脱敏</h2>
            <span>数据可用不可见</span>
          </header>
          <div className="wb-uid-card">
            <div className="wb-uid-row"><span>页面 UID</span><b>SK-2026-000123</b></div>
            <div className="wb-uid-row"><span>姓名</span><b>张*</b></div>
            <div className="wb-uid-row"><span>身份证</span><b>****1234</b></div>
            <div className="wb-uid-row"><span>本人电话</span><b>138****5678</b></div>
          </div>
          <ul className="wb-uid-list">
            <li>UID 与真实学号解耦，页面和导出只出现 UID。</li>
            <li>姓名、身份证、电话默认掩码；家庭住址只保留到市/区。</li>
            <li>UID ↔ 原始记录映射保存在本地数据管理员侧，不进入演示数据库。</li>
            <li>真实数据接入前需学校授权；映射表离线加密，原始文件处理后删除。</li>
          </ul>
          <div className="wb-source">
            数据来源：{metrics.source_files.map((item) => `${item.name}（${fmt(item.rows)} 行）`).join('；')}
          </div>
        </section>
      </div>

      <section className="wb-panel wb-affairs">
        <header className="wb-panel-head">
          <h2>学工业务数据</h2>
          <span>本地资料库中的其他表 · 只做计数，不展开个人明细</span>
        </header>
        <div className="wb-affairs-grid">
          {metrics.affairs.map((item) => (
            <div className="wb-affair" key={item.sheet}>
              <span>{item.sheet.replace(/^\d+_/, '')}</span>
              <b>{fmt(item.rows)}</b>
            </div>
          ))}
          <div className="wb-affair is-accent">
            <span>26 级注册率</span>
            <b>{metrics.registration.new?.rate ?? '—'}%</b>
          </div>
          <div className="wb-affair is-accent">
            <span>老生注册率</span>
            <b>{metrics.registration.old?.rate ?? '—'}%</b>
          </div>
        </div>
      </section>

      <p className="wb-footnote">
        {metrics.disclaimer} · 本地演示版 · 数据生成于 {new Date(metrics.generated_at).toLocaleString('zh-CN', { hour12: false })}
      </p>

      <StudentProfileDrawer
        student={selected}
        changes={selectedChanges}
        open={Boolean(selected)}
        onClose={closeStudent}
        onOpenChanges={(uid) => {
          setSelected(null);
          navigate(`/changes?student=${uid}`);
        }}
        onLocateChange={(changeNo) => {
          setSelected(null);
          navigate(`/changes?change=${changeNo}`);
        }}
      />
    </div>
  );
}
