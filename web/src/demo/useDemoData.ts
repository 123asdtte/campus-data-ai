import { useEffect, useState } from 'react';
import type { DemoData } from './types';
import { getToken, notifySessionExpired, SessionExpiredError } from '../api/auth';

// 页面间共用同一份数据；按 token 区分，避免切换账号后读到上一个身份的范围。
let inFlight: { token: string; promise: Promise<DemoData> } | null = null;
let resolved: { token: string; data: DemoData } | null = null;

function loadDemoData(token: string): Promise<DemoData> {
  if (resolved?.token === token) return Promise.resolve(resolved.data);
  if (inFlight?.token === token) return inFlight.promise;

  const promise = fetch('/demo-api/data', { headers: { Authorization: `Bearer ${token}` } })
    .then((response) => {
      if (response.status === 401) {
        invalidateDemoData();
        notifySessionExpired(token);
        throw new SessionExpiredError();
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json() as Promise<DemoData>;
    })
    .then((payload) => {
      resolved = { token, data: payload };
      return payload;
    })
    .catch((reason: unknown) => {
      if (inFlight?.promise === promise) inFlight = null;
      throw reason;
    });

  inFlight = { token, promise };
  return promise;
}

export function invalidateDemoData(): void {
  inFlight = null;
  resolved = null;
}

export function useDemoData() {
  const [data, setData] = useState<DemoData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setError('登录已失效，请重新登录');
      return;
    }
    let active = true;
    loadDemoData(token)
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '演示数据加载失败');
      });
    return () => {
      active = false;
    };
  }, []);

  return { data, error };
}
