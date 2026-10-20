/**
 * 统一请求封装。
 * - 基址走 VITE_API_BASE，默认 /api（开发期由 Vite 代理到 127.0.0.1:8010）
 * - 超时用 AbortController 控制，避免导入提交无限等待
 * - 错误统一为 ApiError，页面只消费 message
 * - 不在此文件中存放任何凭据；操作人只是展示标识，未经认证
 */

const BASE = import.meta.env.VITE_API_BASE ?? '/api';
const ACTOR = import.meta.env.VITE_ACTOR ?? 'local.operator';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(message: string, status = 0, detail = '') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
}

function buildQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = 15000 } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);

  options.signal?.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Actor': ACTOR,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = '';
      try {
        const payload = (await response.json()) as { detail?: string };
        detail = payload.detail ?? '';
      } catch {
        detail = await response.text().catch(() => '');
      }
      throw new ApiError(detail || `请求失败（HTTP ${response.status}）`, response.status, detail);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`请求超时（${Math.round(timeoutMs / 1000)} 秒），请稍后重试或改用批次号恢复`, 0);
    }
    throw new ApiError('无法连接后端服务，请确认 Import API 容器运行正常', 0);
  } finally {
    window.clearTimeout(timer);
  }
}

export function get<T>(path: string, params: Record<string, unknown> = {}, timeoutMs?: number): Promise<T> {
  return request<T>(`${path}${buildQuery(params)}`, { method: 'GET', timeoutMs });
}

export function post<T>(path: string, body?: unknown, timeoutMs = 60000): Promise<T> {
  return request<T>(path, { method: 'POST', body, timeoutMs });
}

export const actorName = ACTOR;
