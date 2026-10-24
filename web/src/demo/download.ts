import { message } from 'antd';
import { getToken } from '../api/auth';

async function downloadWithAuth(url: string, filename: string, success: string) {
  const token = getToken();
  if (!token) {
    message.error('登录已失效，请重新登录');
    return;
  }
  try {
    const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const payload = await response.json();
        if (payload?.error) detail = payload.error;
      } catch {
        // 非 JSON 错误响应沿用状态码
      }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
    message.success(success);
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : '下载失败');
  }
}

export function downloadFourSheet() {
  return downloadWithAuth('/demo-api/four-sheet', 'four-sheet.xlsx', '四件套已按当前角色下载');
}

export function downloadScopedJson() {
  return downloadWithAuth('/demo-api/data', 'demo-data.json', '当前角色数据已下载');
}
