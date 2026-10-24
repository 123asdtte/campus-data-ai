import { getToken, notifySessionExpired, SessionExpiredError } from './auth';

export interface AssistantCourse {
  weekday: string;
  period: string;
  course: string;
  teacher: string;
  room: string;
  date?: string | null;
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
  note?: string;
  as_of?: string;
  context?: string;
  suggestions?: string[];
  action?: { label: string; to: string } | null;
}

export async function askAssistant(question: string, page: string): Promise<AssistantReply> {
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
      body: JSON.stringify({ question, page }),
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
