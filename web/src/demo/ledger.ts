import { getToken } from '../api/auth';
import type { DemoChange } from './types';

export interface ChangeInput {
  uid: string;
  type: string;
  date: string;
  reason: string;
  target?: string;
}

export interface ImportRow extends ChangeInput {
  change_no?: string;
  status?: string;
}

export interface ImportResult {
  imported: DemoChange[];
  skipped: Array<{ row: number | string; uid?: string; reason: string }>;
  skipped_total: number;
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const token = getToken();
  if (!token) throw new Error('登录已失效，请重新登录');
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  let payload: { error?: string } & Record<string, unknown> = {};
  try {
    payload = await response.json();
  } catch {
    // 非 JSON 响应交给状态码判断
  }
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload as T;
}

export function createChange(input: ChangeInput): Promise<DemoChange> {
  return postJson<{ change: DemoChange }>('/demo-api/changes', { ...input }).then((payload) => payload.change);
}

export function checkChange(changeNo: string): Promise<void> {
  return postJson<{ checked: boolean }>('/demo-api/changes/check', { change_no: changeNo }).then(() => undefined);
}

export function importChanges(changes: ImportRow[]): Promise<ImportResult> {
  return postJson<ImportResult>('/demo-api/changes/import', { changes });
}
