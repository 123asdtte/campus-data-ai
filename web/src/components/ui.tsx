import type { ReactNode } from 'react';

type Tone = 'success' | 'warning' | 'danger' | 'info' | 'muted';

export function PageHeader({
  title,
  description,
  extra,
}: {
  title: string;
  description?: string;
  extra?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {extra && <div>{extra}</div>}
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="stat-tile">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function StatusBadge({ tone, label }: { tone: Tone; label: string }) {
  const className = tone === 'muted' ? 'status' : `status is-${tone}`;
  return (
    <span className={className}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

export function Panel({
  title,
  sub,
  extra,
  flush = false,
  children,
}: {
  title?: string;
  sub?: ReactNode;
  extra?: ReactNode;
  flush?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      {(title || extra) && (
        <header className="panel-head">
          <div>
            {title && <span className="panel-title">{title}</span>}
            {sub && <span className="panel-sub">{sub}</span>}
          </div>
          {extra}
        </header>
      )}
      <div className={flush ? 'panel-body is-flush' : 'panel-body'}>{children}</div>
    </section>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty-state">
      <span className="title">{title}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}
