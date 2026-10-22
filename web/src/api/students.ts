import { buildQuery, get, requestGateway } from './client';
import { isLoggedIn } from './auth';
import type { FilterOptions, Paged, Student, StudentDetail, StudentQuery } from './types';

/**
 * 学生域请求（PR-B 双模式）：
 * - 已登录：经 Java 网关 `/gw/internal/proxy/students`，由网关生成可信签名；
 * - 未登录：保持旧 `/api/students` 行为，避免破坏现有演示页面。
 *
 * 导入域与筛选项仍走旧入口，PR-D 统一收口。
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

  if (isLoggedIn()) {
    return requestGateway<Paged<Student>>(`/internal/proxy/students${buildQuery(params)}`);
  }
  return get<Paged<Student>>('/students', params);
}

export function fetchStudent(studentNo: string): Promise<StudentDetail> {
  const path = `/students/${encodeURIComponent(studentNo)}`;
  if (isLoggedIn()) {
    return requestGateway<StudentDetail>(`/internal/proxy${path}`);
  }
  return get<StudentDetail>(path);
}

export function fetchFilterOptions(): Promise<FilterOptions> {
  return get<FilterOptions>('/meta/filters');
}
