/**
 * 统一请求封装。
 * - 基址走 VITE_API_BASE，默认 /api（开发期由 Vite 代理到 127.0.0.1:8010）
 * - 超时用 AbortController 控制，避免导入提交无限等待
 * - 错误统一为 ApiError，页面只消费 message
 * - 不在此文件中存放任何凭据；操作人只是展示标识，未经认证
 */

import { GW_BASE, GW_CLIENT_ID, getToken } from './auth';

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
  method?: 'GET' | 'POST' | 'PUT';
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export function buildQuery(params: Record<string, unknown>): string {
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

/**
 * 网关请求（PR-B：学生域）。
 *
 * - 已登录时附带 Bearer token 与 clientid，由 Java 网关验签后转发 FastAPI。
 * - RuoYi 的权限/登录错误以 HTTP 200 + {code,msg} 返回，这里统一转成 ApiError。
 * - 未登录时不做拦截，由调用方决定是否跳转登录页。
 */
export async function requestGateway<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, timeoutMs = 15000 } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  options.signal?.addEventListener('abort', () => controller.abort(), { once: true });

  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      clientid: GW_CLIENT_ID,
    };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetch(`${GW_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      throw new ApiError(`网关请求失败（HTTP ${response.status}）`, response.status);
    }
    if (payload && typeof payload === 'object' && typeof (payload as { code?: number }).code === 'number') {
      const wrapped = payload as { code: number; msg?: string };
      if (wrapped.code !== 200) {
        throw new ApiError(wrapped.msg || `网关返回 ${wrapped.code}`, wrapped.code);
      }
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`网关请求超时（${Math.round(timeoutMs / 1000)} 秒）`, 0);
    }
    throw new ApiError('无法连接网关服务，请确认 campus-gateway 容器运行正常', 0);
  } finally {
    window.clearTimeout(timer);
  }
}

export const actorName = ACTOR;
