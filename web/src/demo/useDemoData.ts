import { useEffect, useState } from 'react';
import type { DemoData } from './types';
import { getToken } from '../api/auth';

export function useDemoData() {
  const [data, setData] = useState<DemoData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setError('登录已失效，请重新登录');
      return;
    }
    fetch('/demo-api/data', { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<DemoData>;
      })
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '演示数据加载失败'));
  }, []);

  return { data, error };
}
