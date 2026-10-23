import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GW_CLIENT_ID,
  getLoginUser,
  getToken,
  isLoggedIn,
  login,
  logout,
} from './auth';

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

describe('登录会话', () => {
  it('登录成功后保存 token 与用户名', async () => {
    fetchMock.mockResolvedValue(makeResponse({
      code: 200,
      data: { access_token: 'access-abc', expires_in: 7200 },
    }));

    await login('alice', 'secret');

    expect(getToken()).toBe('access-abc');
    expect(getLoginUser()).toBe('alice');
    expect(isLoggedIn()).toBe(true);

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      clientId: GW_CLIENT_ID,
      grantType: 'password',
      username: 'alice',
      password: 'secret',
    });
  });

  it('业务码失败时抛出服务端消息', async () => {
    fetchMock.mockResolvedValue(makeResponse({ code: 500, msg: '用户名或密码错误' }));

    await expect(login('alice', 'wrong')).rejects.toThrow('用户名或密码错误');
    expect(getToken()).toBeNull();
  });

  it('退出登录清空本地会话', () => {
    window.localStorage.setItem('campus.gateway.token', 'access-abc');
    window.localStorage.setItem('campus.gateway.user', 'alice');

    logout();

    expect(getToken()).toBeNull();
    expect(getLoginUser()).toBeNull();
    expect(isLoggedIn()).toBe(false);
  });
});
