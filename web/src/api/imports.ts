import { get, post } from './client';
import type { BatchDetail, CommitResult, PreviewResult, TargetType, ValidateResult } from './types';

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

export async function previewImport(file: File, targetType: TargetType): Promise<PreviewResult> {
  const content = await fileToBase64(file);
  return post<PreviewResult>(
    '/imports/preview-base64',
    { filename: file.name, content_base64: content, target_type: targetType },
    60000,
  );
}

export function validateImport(batchId: number): Promise<ValidateResult> {
  return post<ValidateResult>(`/imports/${batchId}/validate`, undefined, 60000);
}

export function commitImport(batchId: number): Promise<CommitResult> {
  return post<CommitResult>(`/imports/${batchId}/commit`, undefined, 120000);
}

export function fetchBatch(batchId: number): Promise<BatchDetail> {
  return get<BatchDetail>(`/imports/${batchId}`);
}
