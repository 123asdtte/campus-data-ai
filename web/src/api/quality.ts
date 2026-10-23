import { requestGateway } from './client';
import type { DataQuality } from './types';

/** 数据质量看板：完整性统计与按学院明细。 */
export function fetchDataQuality(): Promise<DataQuality> {
  return requestGateway<DataQuality>('/internal/proxy/meta/data-quality');
}
