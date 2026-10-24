/**
 * PR-B 登录会话（浏览器侧）。
 *
 * 说明：
 * - 登录走网关 `/gw/auth/login`（RuoYi 原生登录），成功后保存 access_token。
 * - token 只存 localStorage，用于开发/测试演示；正式部署应改为 HttpOnly Cookie。
 * - 不在此文件保存任何服务端密钥；HMAC 密钥只在网关与 FastAPI 的环境中。
 */

export const GW_BASE = '/gw';

/** RuoYi 登录使用的固定客户端 ID（与 sys_client 种子数据一致）。 */
export const GW_CLIENT_ID = 'e5cd7e4891bf95d1d19206ce24a7b32e';

const TOKEN_KEY = 'campus.gateway.token';
const USER_KEY = 'campus.gateway.user';
const EXPIRED_KEY = 'campus.gateway.expired';

/** 登录态被网关判定失效时广播，由会话层清空身份并送回登录页。 */
export const SESSION_EXPIRED_EVENT = 'campus:session-expired';

export class SessionExpiredError extends Error {
  constructor(message = '登录状态已失效，请重新登录') {
    super(message);
    this.name = 'SessionExpiredError';
  }
}

export interface LoginResult {
  access_token: string;
  expires_in?: number;
}

export interface SessionInfo {
  user: {
    userName: string;
    nickName: string;
    deptId?: number | string | null;
    dept?: { deptName?: string } | null;
  };
  roles: string[];
  permissions: string[];
}

export function getToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getLoginUser(): string | null {
  return window.localStorage.getItem(USER_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}

export function logout(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

/** 登录页读取并清除“刚刚失效”提示，避免刷新后重复展示。 */
export function consumeExpiredNotice(): boolean {
  const expired = window.sessionStorage.getItem(EXPIRED_KEY) === '1';
  if (expired) window.sessionStorage.removeItem(EXPIRED_KEY);
  return expired;
}

/**
 * 网关返回 401 时统一调用：清 token、留下登录页提示并广播失效事件。
 * 传入失败请求所用的 token，避免旧请求误清新登录的会话。
 */
export function notifySessionExpired(failedToken?: string): void {
  const current = getToken();
  if (!current) return;
  if (failedToken && failedToken !== current) return;
  logout();
  window.sessionStorage.setItem(EXPIRED_KEY, '1');
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

/** 读取网关当前登录用户、角色与权限；角色由服务端账号绑定，不由前端选择。 */
export async function fetchSession(): Promise<SessionInfo> {
  const token = getToken();
  if (!token) throw new Error('未登录');
  const response = await fetch(`${GW_BASE}/system/user/getInfo`, {
    headers: {
      Authorization: `Bearer ${token}`,
      clientid: GW_CLIENT_ID,
    },
  });
  let payload: { code?: number; msg?: string; data?: SessionInfo } = {};
  try {
    payload = await response.json();
  } catch {
    throw new Error(`读取登录身份失败（HTTP ${response.status}）`);
  }
  if (!response.ok || payload.code !== 200 || !payload.data) {
    if (response.status === 401 || payload.code === 401) {
      notifySessionExpired(token);
      throw new SessionExpiredError();
    }
    throw new Error(payload.msg || `读取登录身份失败（HTTP ${response.status}）`);
  }
  return payload.data;
}

/** 网关默认返回英文错误，这里统一转成面向校内用户的提示。 */
function translateLoginError(message: string): string {
  const attempts = message.match(/Password input error (\d+) times/i);
  if (attempts) return `密码不正确（已连续输错 ${attempts[1]} 次）。`;
  if (/user does not exist/i.test(message)) return '账号不存在，请检查学号或工号。';
  if (/user is disabled|account.*disabled/i.test(message)) return '账号已停用，请联系学工处。';
  return message || '登录失败，请稍后重试。';
}

/**
 * 调用 RuoYi 原生登录接口。
 * 返回结构：{ code, msg, data: { access_token, ... } }
 */
export async function login(username: string, password: string): Promise<void> {
  const response = await fetch(`${GW_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      clientId: GW_CLIENT_ID,
      grantType: 'password',
      username,
      password,
      tenantId: '000000',
    }),
  });

  let payload: { code?: number; msg?: string; data?: LoginResult } = {};
  try {
    payload = await response.json();
  } catch {
    throw new Error(`登录失败（HTTP ${response.status}）`);
  }

  if (!response.ok || payload.code !== 200 || !payload.data?.access_token) {
    throw new Error(payload.msg ? translateLoginError(payload.msg) : `登录失败（HTTP ${response.status}）`);
  }

  window.localStorage.setItem(TOKEN_KEY, payload.data.access_token);
  window.localStorage.setItem(USER_KEY, username);
}
