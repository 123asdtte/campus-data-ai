/** 与后端接口字段一一对应，禁止在前端另造字段名。 */

export type StudentStatus = 'enrolled' | 'suspended' | 'withdrawn' | 'graduated' | 'other';
export type ChangeType = 'suspend' | 'resume' | 'withdraw' | 'transfer_major' | 'transfer_school' | 'retain' | 'other';
export type RecordStatus = 'draft' | 'pending_review' | 'confirmed' | 'returned';
export type BatchStatus = 'uploaded' | 'validated' | 'imported' | 'failed';
export type IssueSeverity = 'error' | 'warning';
export type TargetType = 'students' | 'student_changes';

export interface Student {
  id: number;
  student_no: string;
  student_name: string;
  college_name: string | null;
  major_name: string | null;
  class_name: string | null;
  enrollment_year: number | null;
  student_status: StudentStatus;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StudentChange {
  id: number;
  change_type: ChangeType;
  effective_date: string;
  change_reason: string | null;
  record_status: RecordStatus;
  source_batch_id: number | null;
  source_row_number: number | null;
  created_at: string;
}

export interface StudentDetail extends Student {
  changes: StudentChange[];
  change_total: number;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface FilterOptions {
  colleges: string[];
  classes: string[];
  status_counts: Record<string, number>;
  total_active: number;
  change_total: number;
}

export interface RecentBatch {
  id: number;
  batch_code: string;
  source_filename: string;
  target_type: TargetType;
  batch_status: BatchStatus;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  created_at: string;
}

export interface Overview {
  students_active: number;
  students_total: number;
  changes_total: number;
  pending_review: number;
  batches_total: number;
  imported_batches: number;
  last_import_at: string | null;
  open_errors: number;
  status_counts: Record<string, number>;
  change_type_counts: Array<{ change_type: ChangeType; cnt: number }>;
  monthly: Array<{ month: string; cnt: number }>;
  recent_batches: RecentBatch[];
}

export interface StudentQuery {
  keyword?: string;
  college?: string;
  class_name?: string;
  status?: string;
  include_inactive?: boolean;
  page?: number;
  page_size?: number;
}

export interface ImportIssue {
  row_number: number;
  field_name: string | null;
  issue_code: string;
  severity: IssueSeverity;
  issue_message: string;
  issue_status?: string;
}

export interface PreviewResult {
  batch_id: number;
  batch_code: string;
  target_type: TargetType;
  status: string;
  total_rows: number;
  missing_required: string[];
  column_mapping: Record<string, string>;
  unmapped_columns: string[];
  field_labels: Record<string, string>;
  preview: Array<Record<string, unknown>>;
  issues: ImportIssue[];
}

export interface ValidateResult {
  batch_id: number;
  batch_code: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  error_count: number;
  warning_count: number;
  column_mapping: Record<string, string>;
  issues: ImportIssue[];
}

export interface CommitResult {
  batch_id: number;
  batch_code: string;
  status: string;
  inserted_rows: number;
  skipped_rows: Array<{ row_number: number; reason: string }>;
  invalid_rows_excluded: number;
}

export interface BatchDetail {
  batch_id: number;
  batch_code: string;
  source_filename: string;
  target_type: TargetType;
  status: BatchStatus;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  created_by: string | null;
  created_at: string | null;
  finished_at: string | null;
  issues: ImportIssue[];
}

export const STUDENT_STATUS_LABEL: Record<StudentStatus, string> = {
  enrolled: '在校',
  suspended: '休学',
  withdrawn: '退学',
  graduated: '毕业',
  other: '其他',
};

export const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  suspend: '休学',
  resume: '复学',
  withdraw: '退学',
  transfer_major: '转专业',
  transfer_school: '转学',
  retain: '保留学籍',
  other: '其他',
};

export const RECORD_STATUS_LABEL: Record<RecordStatus, string> = {
  draft: '草稿',
  pending_review: '待复核',
  confirmed: '已确认',
  returned: '已退回',
};

export const ISSUE_CODE_LABEL: Record<string, string> = {
  MISSING_REQUIRED: '必填缺失',
  VALUE_TOO_LONG: '超长',
  INVALID_ENUM: '取值不合法',
  INVALID_DATE: '日期非法',
  DUPLICATE_STUDENT_NO: '学号重复',
  UNKNOWN_STUDENT: '学生不存在',
  DUPLICATE_BATCH: '重复文件',
  COLUMN_MAPPING_REQUIRED: '缺必需列',
};
