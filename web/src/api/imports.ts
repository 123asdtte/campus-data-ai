import { requestGateway } from './client';
import type { BatchDetail, CommitResult, PreviewResult, TargetType, ValidateResult } from './types';

/**
 * 导入域请求（PR-D）：
 * - 统一经 Java 网关 `/gw/internal/proxy/imports*`，由网关生成可信签名；
 * - 上传仍走 base64 JSON（10MB 文件编码后约 13.4MB），避免浏览器 multipart 与签名摘要不一致。
 */

/** 读取文件为 base64（去掉 data URL 前缀，后端两种都接受，这里统一发纯 base64）。 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? '');
      const comma = result.indexOf(',');
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error('读取文件失败，请重新选择'));
    reader.readAsDataURL(file);
  });
}

export interface PreviewOptions {
  sheetName?: string;
  headerRow?: number;
  mapping?: Record<string, string | null>;
}

export async function previewImport(
  file: File,
  targetType: TargetType,
  options: PreviewOptions = {},
): Promise<PreviewResult> {
  const content = await fileToBase64(file);
  return requestGateway<PreviewResult>('/internal/proxy/imports/preview-base64', {
    method: 'POST',
    body: {
      filename: file.name,
      content_base64: content,
      target_type: targetType,
      sheet_name: options.sheetName ?? null,
      header_row: options.headerRow ?? null,
      mapping: options.mapping ?? null,
    },
    timeoutMs: 60000,
  });
}

export function remapImport(batchId: number, options: PreviewOptions): Promise<PreviewResult> {
  return requestGateway<PreviewResult>(`/internal/proxy/imports/${batchId}/remap`, {
    method: 'POST',
    body: {
      sheet_name: options.sheetName ?? null,
      header_row: options.headerRow ?? null,
      mapping: options.mapping ?? null,
    },
    timeoutMs: 60000,
  });
}

export function validateImport(batchId: number): Promise<ValidateResult> {
  return requestGateway<ValidateResult>(`/internal/proxy/imports/${batchId}/validate`, {
    method: 'POST',
    timeoutMs: 60000,
  });
}

export function commitImport(batchId: number): Promise<CommitResult> {
  return requestGateway<CommitResult>(`/internal/proxy/imports/${batchId}/commit`, {
    method: 'POST',
    timeoutMs: 120000,
  });
}

export function fetchBatch(batchId: number): Promise<BatchDetail> {
  return requestGateway<BatchDetail>(`/internal/proxy/imports/${batchId}`);
}
