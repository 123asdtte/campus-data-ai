import { requestGateway } from './client';
import type { Overview } from './types';

/** 总览聚合（PR-D）：经 Java 网关，学院范围由签名声明在 SQL 层强制。 */
export function fetchOverview(): Promise<Overview> {
  return requestGateway<Overview>('/internal/proxy/stats/overview', { timeoutMs: 20000 });
}
