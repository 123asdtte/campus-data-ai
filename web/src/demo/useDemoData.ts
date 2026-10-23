import { useEffect, useState } from 'react';
import type { DemoData } from './types';

export function useDemoData() {
  const [data, setData] = useState<DemoData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/demo/demo-data.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<DemoData>;
      })
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '演示数据加载失败'));
  }, []);

  return { data, error };
}
