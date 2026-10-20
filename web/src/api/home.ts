import { get } from './client';
import type { Overview } from './types';

export function fetchOverview(): Promise<Overview> {
  return get<Overview>('/stats/overview', {}, 20000);
}
