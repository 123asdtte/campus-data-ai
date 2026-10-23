import { buildQuery, requestGateway } from './client';
import type { AuditQuery, AuditSummary, PagedAudit } from './types';

/** 全局操作审计（管理员视角）：谁改了什么、改前改后。 */
export function fetchAuditLogs(query: AuditQuery): Promise<PagedAudit> {
  return requestGateway<PagedAudit>(`/internal/proxy/audit-logs${buildQuery({ ...query })}`);
}

/** 按操作人维度的增改删统计（管理员监督视角）。 */
export function fetchAuditSummary(query: {
  from_date?: string;
  until_date?: string;
}): Promise<AuditSummary> {
  return requestGateway<AuditSummary>(`/internal/proxy/audit-logs/summary${buildQuery({ ...query })}`);
}
