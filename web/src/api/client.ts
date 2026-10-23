/**
 * 统一请求封装（PR-D：业务请求唯一入口是 Java 网关 `/gw`）。
 *
 * - 浏览器只携带登录 token 与 clientid，不再发送 `X-Actor`，也无法自行声明角色/学院。
 * - 身份、权限点、数据范围全部由 Java 网关从登录会话生成，FastAPI 二次验签。
 * - 超时用 AbortController 控制，避免导入提交无限等待。
 * - 错误统一为 ApiError，页面只消费 message。
 * - 不在此文件中存放任何凭据或密钥。
 */

import { GW_BASE, GW_CLIENT_ID, getToken } from './auth';

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
  /** 附加请求头（演示态用于携带 X-Actor 操作人；生产态由网关注入，前端不设置）。 */
  headers?: Record<string, string>;
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

/**
 * 网关请求：所有业务页面统一走这里。
 *
 * - 已登录时附带 Bearer token 与 clientid，由 Java 网关验签后转发 FastAPI。
 * - RuoYi 的权限/登录错误以 HTTP 200 + {code,msg} 返回，这里统一转成 ApiError。
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
      ...(options.headers ?? {}),
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
      // FastAPI 直传的 4xx/5xx 错误体形如 {detail: "..."}
      const detail =
        payload && typeof payload === 'object' && typeof (payload as { detail?: string }).detail === 'string'
          ? (payload as { detail: string }).detail
          : `网关请求失败（HTTP ${response.status}）`;
      throw new ApiError(detail, response.status, detail);
    }
    if (payload && typeof payload === 'object' && typeof (payload as { code?: number }).code === 'number') {
      const wrapped = payload as { code: number; msg?: string };
      if (wrapped.code !== 200) {
        throw new ApiError(wrapped.msg || `网关返回 ${wrapped.code}`, wrapped.code);
      }
      // RuoYi 成功响应统一包在 data 里；如果存在 data 则返回 data
      if ('data' in wrapped) {
        return (wrapped as { data: T }).data;
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
