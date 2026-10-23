import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GW_CLIENT_ID } from './auth';
import { ApiError, buildQuery, requestGateway } from './client';

const fetchMock = vi.fn<typeof fetch>();

function makeResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('buildQuery', () => {
  it('过滤空值并保留 0 / false', () => {
    const query = buildQuery({
      keyword: '张 三',
      page: 1,
      page_size: 20,
      empty: '',
      nil: null,
      undef: undefined,
      zero: 0,
      flag: false,
    });

    expect(query).toBe('?keyword=%E5%BC%A0+%E4%B8%89&page=1&page_size=20&zero=0&flag=false');
  });

  it('全部为空时返回空字符串', () => {
    expect(buildQuery({ a: '', b: null, c: undefined })).toBe('');
  });
});

describe('requestGateway', () => {
  it('携带 token、clientid，并解包 RuoYi 的 data', async () => {
    window.localStorage.setItem('campus.gateway.token', 'tok-123');
    fetchMock.mockResolvedValue(makeResponse({ code: 200, data: { id: 7 } }));

    const result = await requestGateway<{ id: number }>('/students/7');

    expect(result).toEqual({ id: 7 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/gw/students/7');
    const headers = init?.headers as Record<string, string>;
    expect(headers.clientid).toBe(GW_CLIENT_ID);
    expect(headers.Authorization).toBe('Bearer tok-123');
  });

  it('未登录时不发送 Authorization', async () => {
    fetchMock.mockResolvedValue(makeResponse({ total: 0 }));

    await requestGateway('/stats/overview');

    const init = fetchMock.mock.calls[0][1];
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it('没有 code 包装时直接返回原始 payload', async () => {
    fetchMock.mockResolvedValue(makeResponse({ total: 2 }));

    await expect(requestGateway('/raw')).resolves.toEqual({ total: 2 });
  });

  it('RuoYi 业务码非 200 时抛出 ApiError', async () => {
    fetchMock.mockResolvedValue(makeResponse({ code: 401, msg: '登录状态已过期' }));

    await expect(requestGateway('/students')).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
      message: '登录状态已过期',
    });
  });

  it('FastAPI 4xx 的 detail 会透传为 ApiError', async () => {
    fetchMock.mockResolvedValue(makeResponse({ detail: '学号格式不正确' }, 400));

    const error = await requestGateway('/students').catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 400, detail: '学号格式不正确' });
  });

  it('HTTP 错误且无 detail 时使用状态码提示', async () => {
    fetchMock.mockResolvedValue(makeResponse(null, 500));

    await expect(requestGateway('/students')).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
      message: '网关请求失败（HTTP 500）',
    });
  });

  it('网络错误转换为可读提示', async () => {
    fetchMock.mockRejectedValue(new TypeError('fetch failed'));

    await expect(requestGateway('/students')).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      message: '无法连接网关服务，请确认 campus-gateway 容器运行正常',
    });
  });

  it('超时中止请求并提示秒数', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((_input, init) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    });

    const promise = requestGateway('/slow', { timeoutMs: 1500 });
    const assertion = expect(promise).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      message: '网关请求超时（2 秒）',
    });
    await vi.advanceTimersByTimeAsync(1501);
    await assertion;
  });
});
