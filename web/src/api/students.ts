import { buildQuery, requestGateway } from './client';
import type { FilterOptions, Paged, Student, StudentDetail, StudentQuery } from './types';

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
