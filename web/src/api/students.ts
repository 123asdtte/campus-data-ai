import { buildQuery, requestGateway } from './client';
import { GW_BASE, GW_CLIENT_ID, getLoginUser, getToken } from './auth';
import { message } from 'antd';
import type {
  FilterOptions,
  Paged,
  Student,
  StudentAuditLog,
  StudentDetail,
  StudentQuery,
} from './types';

/** 可编辑字段，与后端 StudentUpdate 白名单保持一致。 */
export type StudentEditableFields = Pick<
  Student,
  'student_name' | 'class_name' | 'major_name' | 'enrollment_year' | 'student_status'
>;

/**
 * 学生域请求（PR-D）：全部经 Java 网关，浏览器无法自行决定身份与数据范围。
 * 未登录时由路由守卫跳转登录页，不再回落到旧的匿名 `/api` 入口。
 */
export function fetchStudents(query: StudentQuery): Promise<Paged<Student>> {
  const params = {
    keyword: query.keyword,
    college: query.college,
    class_name: query.class_name,
    status: query.status,
    include_inactive: query.include_inactive ?? false,
    page: query.page ?? 1,
    page_size: query.page_size ?? 20,
  };
  return requestGateway<Paged<Student>>(`/internal/proxy/students${buildQuery(params)}`);
}

export function fetchStudent(studentNo: string): Promise<StudentDetail> {
  return requestGateway<StudentDetail>(`/internal/proxy/students/${encodeURIComponent(studentNo)}`);
}

export function fetchFilterOptions(): Promise<FilterOptions> {
  return requestGateway<FilterOptions>('/internal/proxy/meta/filters');
}

/** 单条编辑：仅发送被修改的字段；演示态携带 X-Actor 操作人用于审计留痕。 */
export function updateStudent(
  studentNo: string,
  fields: Partial<StudentEditableFields>,
): Promise<{ student: Student; changed_fields: string[] }> {
  const headers: Record<string, string> = {};
  const actor = getLoginUser();
  if (actor) headers['X-Actor'] = actor;
  return requestGateway(`/internal/proxy/students/${encodeURIComponent(studentNo)}`, {
    method: 'PUT',
    body: fields,
    headers,
  });
}

/** 字段级编辑审计（operation_logs）。 */
export function fetchStudentAudit(
  studentNo: string,
  limit = 30,
): Promise<{ items: StudentAuditLog[]; total: number }> {
  return requestGateway(`/internal/proxy/students/${encodeURIComponent(studentNo)}/audit${buildQuery({ limit })}`);
}

/**
 * 按需字段导出：直接拉取 Excel 流并触发浏览器下载，不经 JSON 解析。
 * 导出范围与当前筛选条件一致（keyword/college/class_name/status/include_inactive）。
 * splitByCollege=true 时每个学院单独一个工作表。
 */
export function exportStudents(query: StudentQuery, fields: string[], splitByCollege = false): void {
  const qs = buildQuery({
    keyword: query.keyword,
    college: query.college,
    class_name: query.class_name,
    status: query.status,
    include_inactive: query.include_inactive ?? false,
    split_by_college: splitByCollege || undefined,
    fields: fields.join(','),
  });
  const headers: Record<string, string> = { clientid: GW_CLIENT_ID };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  fetch(`${GW_BASE}/internal/proxy/students/export${qs}`, { headers })
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `学生信息_${Date.now()}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      message.success('导出成功，已开始下载');
    })
    .catch(() => message.error('导出失败，请稍后重试'));
}
