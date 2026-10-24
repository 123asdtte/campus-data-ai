import { getToken, notifySessionExpired, SessionExpiredError } from './auth';

export interface AssistantCourse {
  weekday: string;
  period: string;
  course: string;
  teacher: string;
  room: string;
  date?: string | null;
}

export interface AssistantStudent {
  uid: string;
  name: string;
  college: string;
  major: string;
  class_name: string;
  class_short: string;
  status: string;
  status_tone: string;
  counselor: string;
  change_count: number;
  profile_to: string;
}

export interface AssistantReply {
  intent: string;
  answer: string;
  scope: {
    label?: string;
    date?: string | null;
    weekday?: string | null;
    week?: number;
    period?: string | null;
  };
  courses: AssistantCourse[];
  students?: AssistantStudent[];
  student_total?: number;
  note?: string;
  as_of?: string;
  context?: string;
  suggestions?: string[];
  action?: { label: string; to: string } | null;
}

export async function askAssistant(
  question: string,
  page: string,
  context?: { student_uid?: string; change_no?: string },
): Promise<AssistantReply> {
  const token = getToken();
  if (!token) throw new SessionExpiredError();

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch('/demo-api/assistant/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ question, page, context }),
      signal: controller.signal,
    });

    if (response.status === 401) {
      notifySessionExpired(token);
      throw new SessionExpiredError();
    }

    const payload = (await response.json().catch(() => null)) as
      | (AssistantReply & { error?: string })
      | null;
    if (!response.ok || !payload) {
      // 限流与并发满的响应体不是本服务的 JSON（来自 nginx / demo-api），要给出可行动的提示而不是 HTTP 码
      if (response.status === 429) throw new Error('问数请求过于频繁，请稍候十几秒再问一次。');
      if (response.status === 503) throw new Error('演示服务并发已满，请稍后重试。');
      if (response.status === 403) throw new Error(payload?.error || '当前账号没有使用该问数范围的权限。');
      throw new Error(payload?.error || `查询失败（HTTP ${response.status}）`);
    }
    return payload;
  } catch (reason) {
    if (reason instanceof SessionExpiredError) throw reason;
    if (reason instanceof DOMException && reason.name === 'AbortError') {
      throw new Error('查询超时，请重试。');
    }
    if (reason instanceof Error) throw reason;
    throw new Error('网络异常，请重试。');
  } finally {
    window.clearTimeout(timer);
  }
}
