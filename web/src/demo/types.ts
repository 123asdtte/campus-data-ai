export type Tone = 'success' | 'info' | 'warning' | 'danger' | 'muted';

export interface NameCount {
  name: string;
  count: number;
  tone?: Tone;
  active?: number;
}

export interface QualityItem {
  count: number;
  label: string;
  description: string;
  examples?: Array<Record<string, unknown>>;
  class_names?: number;
  admitted_not_in_roster?: number;
  roster_2026_not_admitted?: number;
  admissions_rows?: number;
  roster_2026_rows?: number;
}

export interface DemoStudent {
  uid: string;
  name: string;
  gender: string;
  college: string;
  major: string;
  class_name: string;
  class_short: string;
  grade: string;
  enrollment_year: number | null;
  status: string;
  status_tone: Tone;
  counselor: string;
  phone: string;
  id_card: string;
  source_region: string;
  is_active: boolean;
  change_count: number;
  flags: string[];
}

export interface ScheduleRow {
  class_name: string;
  class_short: string;
  course: string;
  teacher: string;
  weekday: string;
  period: string;
  weeks: string;
  room: string;
  campus: string;
  term: string;
  note: string;
}

export interface PeriodTime {
  period: string;
  start: string;
  end: string;
  slot: string;
}

export interface ScheduleMeta {
  rows: number;
  unmatched_rows: number;
  classes: number;
  current_week: number;
  period_times: PeriodTime[];
  note: string;
}

export interface DemoChange {
  uid: string;
  change_no: string;
  type: string;
  reason: string;
  date: string;
  target: string;
  status: string;
  created_by?: string;
  created_at?: string;
}

export interface DemoData {
  meta: {
    title: string;
    source: string;
    data_nature: string;
    uid_rule: string;
    generated_at: string;
  };
  metrics: {
    disclaimer: string;
    generated_at: string;
    source: string;
    total_students: number;
    total_classes: number;
    roster_class_names: number;
    total_colleges: number;
    total_majors: number;
    total_counselors: number;
    status_counts: NameCount[];
    college_counts: NameCount[];
    grade_counts: NameCount[];
    top_majors: NameCount[];
    change_total: number;
    change_type_counts: NameCount[];
    change_status_counts: NameCount[];
    orphan_changes: number;
    registration: Record<string, { label: string; classes: number; total: number; registered: number; rate: number | null }>;
    data_quality: Record<string, QualityItem>;
    affairs: Array<{ sheet: string; rows: number }>;
    source_files: Array<{ name: string; rows: number }>;
    schedule_meta: ScheduleMeta;
  };
  students: DemoStudent[];
  schedule: ScheduleRow[];
  changes: DemoChange[];
  platform_checked?: string[];
  class_summary: Array<{
    class_name: string;
    class_short: string;
    class_code: string;
    college: string;
    major: string;
    counselor: string;
    students: number;
    status: Record<string, number>;
  }>;
  anomalies: QualityItem[];
}
