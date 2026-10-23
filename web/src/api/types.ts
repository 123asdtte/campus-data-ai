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

/** 字段级编辑审计（对应后端 campus.operation_logs）。 */
export interface StudentAuditLog {
  id: number;
  actor_user_id: string | null;
  actor_db_role: string;
  action: 'insert' | 'update' | 'delete';
  object_type: string;
  object_id: string | null;
  changed_fields: string[] | null;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  result: string;
  created_at: string;
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

/** 可导出字段选项（与后端 EXPORT_FIELD_LABELS 白名单保持一致）。 */
export const EXPORT_FIELD_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'student_no', label: '学号' },
  { value: 'student_name', label: '姓名' },
  { value: 'college_name', label: '学院' },
  { value: 'major_name', label: '专业' },
  { value: 'class_name', label: '班级' },
  { value: 'enrollment_year', label: '入学年份' },
  { value: 'student_status', label: '在校状态' },
];

/** 全局操作审计条目（后端 /audit-logs，学生类关联出学号与姓名）。 */
export interface AuditLogEntry {
  id: number;
  created_at: string;
  actor_user_id: string | null;
  actor_db_role: string;
  action: 'insert' | 'update' | 'delete';
  object_type: string;
  object_id: string | null;
  student_no: string | null;
  student_name: string | null;
  changed_fields: string[] | null;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  result: string;
}

export interface AuditQuery {
  keyword?: string;
  actor?: string;
  action?: string;
  from_date?: string;
  until_date?: string;
  page?: number;
  page_size?: number;
}

export interface PagedAudit {
  items: AuditLogEntry[];
  total: number;
}

/** 按操作人维度的增改删统计（后端 /audit-logs/summary）。 */
export interface AuditSummaryItem {
  actor_user_id: string | null;
  actor_db_role: string;
  display_name: string;
  total: number;
  inserts: number;
  updates: number;
  deletes: number;
}

export interface AuditSummary {
  items: AuditSummaryItem[];
}

/** 数据质量看板（后端 /meta/data-quality）。 */
export interface DataQualityCollege {
  college_name: string;
  total: number;
  missing_major: number;
  missing_class: number;
  missing_year: number;
  complete: number;
}

export interface DataQuality {
  total: number;
  missing_college: number;
  missing_major: number;
  missing_class: number;
  missing_year: number;
  complete: number;
  duplicate_names: number;
  by_college: DataQualityCollege[];
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
  sheet_name: string;
  header_row: number;
  sheets: SheetInfo[];
  needs_sheet_choice: boolean;
  missing_required: string[];
  column_mapping: Record<string, string>;
  mapping: ColumnMapping[];
  unmapped_columns: string[];
  conflicts: string[];
  ambiguous: string[];
  field_labels: Record<string, string>;
  preview: Array<Record<string, unknown>>;
  issues: ImportIssue[];
}

export interface SheetInfo {
  name: string;
  header_row: number;
  data_rows: number;
  matched: number;
  matched_required: number;
  score: number;
}

export interface ColumnMapping {
  source: string;
  target: string | null;
  target_label: string;
  confidence: number;
  method: string;
  status: 'matched' | 'ambiguous' | 'conflict' | 'unmatched';
  candidates: Array<{ field: string; label: string; confidence: number }>;
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
