export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const CN_DAYS: Record<string, string> = {
  一: '周一',
  二: '周二',
  三: '周三',
  四: '周四',
  五: '周五',
  六: '周六',
  日: '周日',
  天: '周日',
};

export function normalizeWeekday(value: unknown): string {
  const text = String(value ?? '').trim();
  if (WEEKDAYS.includes(text)) return text;
  if (/^[1-7]$/.test(text)) return WEEKDAYS[Number(text) - 1];
  const bare = text.replace(/星期|礼拜|周/g, '');
  return CN_DAYS[bare] ?? text;
}

export function weekMatches(weeks: string, currentWeek: number): boolean {
  const text = weeks || '';
  if (!text) return true;
  if (text.includes('单') && currentWeek % 2 === 0) return false;
  if (text.includes('双') && currentWeek % 2 === 1) return false;
  const ranges = [...text.matchAll(/(\d+)\s*-\s*(\d+)/g)];
  if (ranges.length) {
    return ranges.some((range) => currentWeek >= Number(range[1]) && currentWeek <= Number(range[2]));
  }
  const numbers = [...text.matchAll(/\d+/g)].map((item) => Number(item[0]));
  return !numbers.length || numbers.includes(currentWeek);
}

export function periodNumbers(period: string): number[] {
  return [...String(period ?? '').matchAll(/\d+/g)].map((item) => Number(item[0]));
}

export function periodRank(period: string): number {
  const numbers = periodNumbers(period);
  return numbers.length ? Math.min(...numbers) : 99;
}

export function currentDayName(now = new Date()): string {
  return WEEKDAYS[(now.getDay() + 6) % 7];
}
