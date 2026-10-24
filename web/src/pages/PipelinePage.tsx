import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Spin,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckCircleOutlined, InboxOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/ui';
import { fmt } from '../demo/format';
import { useDemoData } from '../demo/useDemoData';
import { downloadFourSheet, downloadScopedJson } from '../demo/download';

const STEPS = [
  { key: 'identify', title: '识别文件类型', detail: '按表头判断：花名册 / 学籍异动 / 招生录取 / 学工业务。' },
  { key: 'map', title: '字段映射', detail: '原始字段 → 标准字段；不确定的标“待人工确认”，不猜测合并。' },
  { key: 'clean', title: '清洗', detail: '学号去空格、全角转半角、日期统一、身份证 X 大写、班级归一、去重。' },
  { key: 'match', title: '与底账核对', detail: '以学号为键比对花名册：学号不存在、姓名/班级不一致、状态异常。' },
  { key: 'output', title: '输出四件套', detail: '标准化数据 / 异常清单 / 字段映射 / 核对汇总。' },
  { key: 'ledger', title: '登记台账', detail: '每次处理留一行：登记编号、来源、原文件名、归档名、处理状态。' },
];

interface LedgerRow {
  key: string;
  no: string;
  source: string;
  file: string;
  rows: number;
  type: string;
  status: string;
}

export default function PipelinePage() {
  const { data, error } = useDemoData();
  const [activeStep, setActiveStep] = useState(0);
  const [running, setRunning] = useState(false);
  const [finished, setFinished] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  const sourceCards = useMemo(() => {
    if (!data) return [];
    const affairsRows = data.metrics.affairs.reduce((sum, item) => sum + item.rows, 0);
    return [
      { name: '05_学生花名册.xlsx', rows: data.metrics.source_files.find((item) => item.name.includes('花名册'))?.rows ?? 0, kind: '全校底账', tone: 'green' },
      { name: '04_班级信息表.xlsx', rows: data.metrics.source_files.find((item) => item.name.includes('班级'))?.rows ?? 0, kind: '组织基础', tone: 'blue' },
      { name: '10_学籍异动记录表.xlsx', rows: data.metrics.source_files.find((item) => item.name.includes('异动'))?.rows ?? 0, kind: '学籍异动', tone: 'orange' },
      { name: '13_招生录取数据（UTF-8）.csv', rows: data.metrics.source_files.find((item) => item.name.includes('招生'))?.rows ?? 0, kind: '招生来源', tone: 'purple' },
      { name: '学工业务数据_2026年9-10月.xlsx', rows: affairsRows, kind: '学工 8 张表', tone: 'red' },
    ];
  }, [data]);

  const ledger: LedgerRow[] = useMemo(() => {
    if (!data) return [];
    const rows = sourceCards.map((item, index) => ({
      key: `${index}`,
      no: `DJ2026-${String(index + 1).padStart(3, '0')}`,
      source: item.kind,
      file: item.name,
      rows: item.rows,
      type: item.kind,
      status: index < 2 ? '已归档 · 未并入底账' : '已识别 · 待复核',
    }));
    return rows;
  }, [data, sourceCards]);

  if (error) {
    return <Alert type="error" showIcon message="演示数据加载失败" description={error} />;
  }

  if (!data) {
    return <div className="wb wb-loading"><Spin size="large" /><span>正在加载本地演示数据…</span></div>;
  }

  const start = () => {
    if (running) return;
    setActiveStep(0);
    setFinished(false);
    setRunning(true);
    let step = 0;
    timer.current = window.setInterval(() => {
      step += 1;
      setActiveStep(step);
      if (step >= STEPS.length) {
        if (timer.current) window.clearInterval(timer.current);
        timer.current = null;
        setRunning(false);
        setFinished(true);
        void message.success(`整理完成：${fmt(data.metrics.total_students)} 名学生，四件套已生成`);
      }
    }, 520);
  };

  const quality = data.metrics.data_quality;
  const qualityCount = ['duplicate_rows', 'same_name_groups', 'id_invalid', 'class_not_found', 'transfer_conflicts']
    .reduce((sum, key) => sum + (quality[key]?.count ?? 0), 0);

  const columns: ColumnsType<LedgerRow> = [
    { title: '登记编号', dataIndex: 'no', width: 120, render: (value: string) => <span className="wb-mono">{value}</span> },
    { title: '来源', dataIndex: 'source', width: 110 },
    { title: '原文件名', dataIndex: 'file', render: (value: string) => <span className="wb-mono">{value}</span> },
    { title: '识别类型', dataIndex: 'type', width: 110, render: (value: string) => <Tag>{value}</Tag> },
    { title: '行数', dataIndex: 'rows', width: 90, render: (value: number) => <span className="wb-mono">{fmt(value)}</span> },
    { title: '处理状态', dataIndex: 'status', width: 170, render: (value: string) => <Tag color={value.includes('已归档') ? 'green' : 'orange'}>{value}</Tag> },
  ];

  return (
    <div className="wb">
      <PageHeader
        title="资料库 / 收件箱"
        description="老师把表原样放进收件箱，系统识别、映射、清洗、与底账核对，输出四件套并登记台账。演示版使用已生成的虚构数据跑完整流程。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">WORKBUDDY → LOCAL</span>
            <span className="wb-badge is-demo">演示数据 · 预生成流程</span>
          </div>
        }
      />

      <div className="pl-hero">
        <div className="pl-hero-copy">
          <div className="pl-kicker">INBOX → STANDARDIZED DATA → LEDGER</div>
          <h2>把“收件箱”变成一条可复核的流水线。</h2>
          <p>同一套规则：原始文件不覆盖、敏感字段不补齐、业务规则不猜测、产物先人工复核。演示数据来自 WorkBuddy 试点交付材料。</p>
          <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={running} onClick={start}>
            {finished ? '再整理一次' : running ? '正在整理…' : '开始整理收件箱'}
          </Button>
        </div>
        <div className="pl-source-list">
          {sourceCards.map((item, index) => (
            <div className={`pl-source${activeStep > index && activeStep < STEPS.length ? ' is-touched' : ''}`} key={item.name}>
              <span className={`pl-source-dot is-${item.tone}`} />
              <div>
                <b>{item.name}</b>
                <small>{item.kind} · {fmt(item.rows)} 行</small>
              </div>
              {finished || activeStep === STEPS.length ? (
                <CheckCircleOutlined className="pl-source-check" />
              ) : (
                <span className="pl-source-state">待整理</span>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="pl-steps">
        {STEPS.map((step, index) => {
          const done = finished || activeStep > index;
          const active = !finished && activeStep === index && running;
          return (
            <div className={`pl-step${done ? ' is-done' : ''}${active ? ' is-active' : ''}`} key={step.key}>
              <span className="pl-step-no">{done ? <CheckCircleOutlined /> : String(index + 1).padStart(2, '0')}</span>
              <b>{step.title}</b>
              <p>{step.detail}</p>
            </div>
          );
        })}
      </div>

      <div className="wb-grid pl-results">
        <section className="wb-panel">
          <header className="wb-panel-head"><h2>整理结果</h2><span>{finished ? '四件套已生成' : '点击开始整理'}</span></header>
          <div className="pl-result-grid">
            <div><span>标准化学生</span><b>{fmt(data.metrics.total_students)}</b></div>
            <div><span>需核对项</span><b className="is-warn">{fmt(qualityCount)}</b></div>
            <div><span>异动记录</span><b>{fmt(data.metrics.change_total)}</b></div>
            <div><span>同班同名</span><b>{fmt(quality.same_name_groups?.count ?? 0)}</b></div>
          </div>
          <div className="pl-sheet-links">
            <button type="button" className="wb-download" onClick={() => void downloadFourSheet()}>
              <InboxOutlined /> 四件套 Excel
            </button>
            <button type="button" className="wb-download" onClick={() => void downloadScopedJson()}>
              当前角色数据 JSON
            </button>
          </div>
          <p className="wb-note">四件套：标准化数据 / 异常清单 / 字段映射 / 核对汇总。仅用于演示与人工复核。</p>
        </section>

        <section className="wb-panel">
          <header className="wb-panel-head"><h2>待人工确认</h2><span>不猜测、不补齐</span></header>
          <div className="pl-confirm-list">
            <div><span>班级名称未匹配</span><b>{fmt(quality.class_not_found?.count ?? 0)} 人 / {quality.class_not_found?.class_names ?? 0} 个班名</b></div>
            <div><span>转专业已批但花名册未更新</span><b>{fmt(quality.transfer_conflicts?.count ?? 0)} 条</b></div>
            <div><span>身份证校验异常</span><b>{fmt(quality.id_invalid?.count ?? 0)} 条</b></div>
            <div><span>同名同姓提示</span><b>{fmt(quality.same_name_all?.count ?? 0)} 组</b></div>
            <div><span>招生与 2026 级口径差异</span><b>{fmt(quality.admissions?.count ?? 0)} 条</b></div>
          </div>
          <p className="wb-note">以上差异进入待确认清单，由老师判定；系统不会自动改写底账。</p>
        </section>
      </div>

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head"><h2>文件登记台账</h2><span>每次处理留一行 · 演示数据</span></header>
        {ledger.length ? (
          <Table<LedgerRow> rowKey="key" size="middle" columns={columns} dataSource={ledger} pagination={false} scroll={{ x: 900 }} />
        ) : (
          <Empty description="暂无台账" />
        )}
      </section>

      <section className="wb-panel">
        <header className="wb-panel-head"><h2>四条红线</h2><span>与 WorkBuddy 试点一致</span></header>
        <div className="pl-rules">
          <div><b>01</b><span>原始文件不覆盖，所有输出为新文件。</span></div>
          <div><b>02</b><span>身份证、考生号、家长电话缺失时留空并列异常，不编造。</span></div>
          <div><b>03</b><span>转专业、招生方式等业务规则不确定时进待确认，由老师判定。</span></div>
          <div><b>04</b><span>产物先人工复核，再进入使用或归档。</span></div>
        </div>
      </section>

      <p className="wb-footnote">{data.metrics.disclaimer} · 资料库流水线演示 · 本地生成，不上传云端</p>
    </div>
  );
}
