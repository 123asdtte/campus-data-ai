import { get } from './client';
import type { FilterOptions, Paged, Student, StudentDetail, StudentQuery } from './types';

export function fetchStudents(query: StudentQuery): Promise<Paged<Student>> {
  return get<Paged<Student>>('/students', {
    keyword: query.keyword,
    college: query.college,
    class_name: query.class_name,
    status: query.status,
    include_inactive: query.include_inactive ?? false,
    page: query.page ?? 1,
    page_size: query.page_size ?? 20,
  });
}

export function fetchStudent(studentNo: string): Promise<StudentDetail> {
  return get<StudentDetail>(`/students/${encodeURIComponent(studentNo)}`);
}

export function fetchFilterOptions(): Promise<FilterOptions> {
  return get<FilterOptions>('/meta/filters');
}
