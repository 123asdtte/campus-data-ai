import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plot } from '@lucasmarkes/hairline/react';
import { ApiError } from '../api/client';
import { fetchOverview } from '../api/home';
import type { BatchStatus, Overview } from '../api/types';
import { CHANGE_TYPE_LABEL } from '../api/types';

const BATCH_LABEL: Record<BatchStatus, string> = {
  uploaded: '已上传',
  validated: '待提交',
  imported: '已导入',
  failed: '失败',
};

const BATCH_TONE: Record<BatchStatus, 'is-hi' | 'is-edge' | 'is-lo'> = {
  imported: 'is-hi',
  validated: 'is-edge',
  uploaded: 'is-lo',
  failed: 'is-lo',
};

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function HomePage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchOverview()
      .then(setData)
      .catch((err: ApiError) => setError(err.message || '加载失败'));
  }, []);

  const maxChange = Math.max(1, ...(data?.change_type_counts ?? []).map((item) => item.cnt));
  const maxMonth = Math.max(1, ...(data?.monthly ?? []).map((item) => item.cnt));

  return (
    <div className="hv">
      <section className="hv-hero">
        <div className="hv-hero-copy">
          <div className="hv-kicker">郴州思科职业学院 / 数据管理平台</div>
          <h1 className="hv-headline">
            分散的表格，
            <br />
            收进一条可追溯的线里。
          </h1>
          <p className="hv-lede">
            面向学工与教务的本地数据工具：学生信息与导入批次经网关入库，异动台账另有本地演示数据集（见下方口径说明）。每份表格先预览、再校验、后提交，每次写入都留在审计记录里。
          </p>
          <div className="hv-actions">
            <Link className="hv-link" to="/students">
              进入学生信息 <span>→</span>
            </Link>
            <Link className="hv-link is-quiet" to="/import">
              导入一份表格 <span>→</span>
            </Link>
            <Link className="hv-link is-quiet" to="/workbench">
              打开数据工作台 <span>→</span>
            </Link>
          </div>
        </div>
        <div className="hv-figure" aria-hidden>
          <Plot intensity={0.65} label="数据分布示意" />
        </div>
      </section>

      <section className="hv-metrics">
        <div className="hv-metric">
          <div className="hv-metric-label">在校学生</div>
          <div className="hv-metric-value">{data?.students_active ?? '—'}</div>
          <div className="hv-metric-hint">
            档案总数 {data?.students_total ?? '—'}
          </div>
        </div>
        <div className="hv-metric">
          <div className="hv-metric-label">学籍异动</div>
          <div className="hv-metric-value">{data?.changes_total ?? '—'}</div>
          <div className="hv-metric-hint">待复核 {data?.pending_review ?? '—'}</div>
        </div>
        <div className="hv-metric">
          <div className="hv-metric-label">导入批次</div>
          <div className="hv-metric-value">{data?.batches_total ?? '—'}</div>
          <div className="hv-metric-hint">成功 {data?.imported_batches ?? '—'}</div>
        </div>
        <div className="hv-metric">
          <div className="hv-metric-label">待处理错误</div>
          <div className="hv-metric-value">{data?.open_errors ?? '—'}</div>
          <div className="hv-metric-hint">来自导入异常明细</div>
        </div>
      </section>
      <p className="hv-source">
        本页数字来自网关库（学生信息与导入批次写入的同一套库）。数据工作台与学籍异动台账读的是
        <code>demo-api</code> 的本地演示数据集，两套数据彼此独立、条数不一致属预期，不是同步失败。
      </p>

      {error && (
        <div className="hv-error">
          <span>数据加载失败：{error}</span>
          <button type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
        </div>
      )}

      <div className="hv-grid">
        <section className="hv-block">
          <header className="hv-block-head">
            <span className="hv-index">01</span>
            <h2 className="hv-block-title">学籍异动分布</h2>
            <span className="hv-block-meta">按类型</span>
          </header>
          <div className="hv-bars">
            {(data?.change_type_counts ?? []).map((item) => (
              <div className="hv-bar-row" key={item.change_type}>
                <span className="hv-bar-label">
                  {CHANGE_TYPE_LABEL[item.change_type] ?? item.change_type}
                </span>
                <span className="hv-bar-track">
                  <span
                    className="hv-bar-fill"
                    style={{ width: `${Math.round((item.cnt / maxChange) * 100)}%` }}
                  />
                </span>
                <span className="hv-bar-count">{item.cnt}</span>
              </div>
            ))}
            {!data && <div className="hv-placeholder">加载中</div>}
          </div>
        </section>

        <section className="hv-block">
          <header className="hv-block-head">
            <span className="hv-index">02</span>
            <h2 className="hv-block-title">最近导入</h2>
            <Link className="hv-block-meta hv-block-link" to="/import">
              全部
            </Link>
          </header>
          <div className="hv-rows">
            {(data?.recent_batches ?? []).map((batch) => (
              <div className="hv-row" key={batch.id}>
                <span className="hv-row-main">
                  <span className={`hv-dot ${BATCH_TONE[batch.batch_status]}`} />
                  <span className="hv-row-name">{batch.source_filename}</span>
                </span>
                <span className="hv-row-meta">
                  {BATCH_LABEL[batch.batch_status]} · {batch.valid_rows}/{batch.total_rows} 行
                </span>
                <span className="hv-row-time">{formatDate(batch.created_at)}</span>
              </div>
            ))}
            {!data && <div className="hv-placeholder">加载中</div>}
            {data && data.recent_batches.length === 0 && (
              <div className="hv-placeholder">还没有导入记录</div>
            )}
          </div>
        </section>
      </div>

      <section className="hv-block hv-block-wide">
        <header className="hv-block-head">
          <span className="hv-index">03</span>
          <h2 className="hv-block-title">近六个月异动发生量</h2>
          <span className="hv-block-meta">按生效月份</span>
        </header>
        <div className="hv-trend">
          {(data?.monthly ?? []).map((item) => (
            <div className="hv-trend-col" key={item.month}>
              <span className="hv-trend-count">{item.cnt}</span>
              <span className="hv-trend-track">
                <span
                  className="hv-trend-fill"
                  style={{ height: `${Math.max(2, Math.round((item.cnt / maxMonth) * 100))}%` }}
                />
              </span>
              <span className="hv-trend-label">{item.month.slice(2).replace('-', '/')}</span>
            </div>
          ))}
          {!data && <div className="hv-placeholder">加载中</div>}
        </div>
      </section>

      <footer className="hv-foot">
        <span>郴州思科职业学院 · 数据管理平台</span>
        <span>校训 · 自立自强　兼济天下</span>
        <span>本地测试 · 虚构数据 · 最近导入 {formatDate(data?.last_import_at ?? null)}</span>
      </footer>
    </div>
  );
}
