-- =====================================================================
-- 一期虚构演示数据（不含任何真实学生信息）
-- 规模：学生 200 条、学籍异动 300 条、历史导入批次 1 条
-- 特性：可重复执行 —— 先按批次与学号前缀清理，再重新生成
-- 执行：psql -v ON_ERROR_STOP=1 -f sql/002_seed_demo.sql
-- =====================================================================

BEGIN;
SET search_path TO campus, public;

-- 幂等清理：仅删除本脚本生成的数据
DELETE FROM campus.operation_logs
WHERE object_type IN ('students', 'student_changes')
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+08';

DELETE FROM campus.import_issues
WHERE batch_id IN (SELECT id FROM campus.import_batches WHERE batch_code LIKE 'DEMO-%');

DELETE FROM campus.import_batches WHERE batch_code LIKE 'DEMO-%';

DELETE FROM campus.student_changes
WHERE student_id IN (SELECT id FROM campus.students WHERE student_no LIKE 'DEMO%');

DELETE FROM campus.students WHERE student_no LIKE 'DEMO%';

-- ---------------------------------------------------------------------
-- 学生：200 条
-- 学号规则 DEMO + 入学年份 + 学院码 + 4 位序号（虚构）
-- ---------------------------------------------------------------------
WITH college_major AS (
    SELECT row_number() OVER (ORDER BY college_code, major_name) AS idx,
           college_code, college_name, major_name
    FROM (VALUES
        (1, '计算机学院',     '软件技术'),
        (1, '计算机学院',     '大数据技术'),
        (2, '电子信息学院',   '电子信息工程技术'),
        (2, '电子信息学院',   '物联网应用技术'),
        (3, '机械工程学院',   '机电一体化技术'),
        (3, '机械工程学院',   '数控技术'),
        (4, '经济管理学院',   '大数据与会计'),
        (4, '经济管理学院',   '现代物流管理'),
        (5, '外国语学院',     '商务英语'),
        (5, '外国语学院',     '应用日语'),
        (6, '艺术设计学院',   '视觉传达设计'),
        (6, '艺术设计学院',   '数字媒体艺术设计')
    ) AS t(college_code, college_name, major_name)
),
surnames AS (
    SELECT ARRAY['张','王','李','赵','刘','陈','杨','黄','周','吴',
                 '徐','孙','马','朱','胡','郭','何','高','林','罗'] AS a
),
given AS (
    SELECT ARRAY['伟','芳','娜','敏','静','磊','洋','勇','艳','杰',
                 '娟','涛','明','超','秀英','霞','平','刚','桂英','鹏',
                 '宇','晨','雨','欣','浩','然','佳','琪','博','宁'] AS a
),
src AS (
    SELECT g,
           2021 + (g % 4)                    AS enroll_year,
           1 + ((g * 7) % 12)                AS cm_idx,
           1 + ((g * 3) % 20)                AS s_idx,
           1 + ((g * 11) % 30)               AS g_idx,
           CASE
               WHEN g % 97 = 0 THEN 'withdrawn'
               WHEN g % 53 = 0 THEN 'suspended'
               WHEN g % 41 = 0 THEN 'graduated'
               ELSE 'enrolled'
           END                               AS status
    FROM generate_series(1, 200) AS g
)
INSERT INTO campus.students (student_no, student_name, college_name, major_name, class_name, enrollment_year, student_status)
SELECT 'DEMO' || s.enroll_year::text || lpad(cm.college_code::text, 2, '0') || lpad(s.g::text, 4, '0'),
       su.a[s.s_idx] || gi.a[s.g_idx],
       cm.college_name,
       cm.major_name,
       cm.major_name || ((s.g % 4) + 1)::text || '级' || (1 + (s.g % 3))::text || '班',
       s.enroll_year,
       s.status
FROM src s
JOIN college_major cm ON cm.idx = s.cm_idx
CROSS JOIN surnames su
CROSS JOIN given gi
ORDER BY s.g;

-- ---------------------------------------------------------------------
-- 学籍异动：300 条（每名学生 1~3 条，日期落在 2024-09 ~ 2026-09）
-- ---------------------------------------------------------------------
WITH numbered AS (
    SELECT id, row_number() OVER (ORDER BY student_no) AS rn
    FROM campus.students
    WHERE student_no LIKE 'DEMO%'
)
INSERT INTO campus.student_changes (student_id, change_type, effective_date, change_reason, record_status)
SELECT n.id,
       (ARRAY['suspend','resume','withdraw','transfer_major','transfer_school','retain','other'])[1 + ((g * 5) % 7)],
       DATE '2024-09-01' + ((g * 23) % 730),
       (ARRAY[
           '因个人身体原因申请休学一学期',
           '休学期满申请复学',
           '家庭原因申请退学',
           '依据个人志愿调整专业',
           '因家庭搬迁申请转学',
           '参军入伍申请保留学籍',
           '其他学籍异动，待补充说明'
       ])[1 + ((g * 5) % 7)],
       CASE
           WHEN g % 11 = 0 THEN 'draft'
           WHEN g % 7  = 0 THEN 'pending_review'
           WHEN g % 17 = 0 THEN 'returned'
           ELSE 'confirmed'
       END
FROM generate_series(1, 300) AS g
JOIN numbered n ON n.rn = 1 + ((g * 7) % 200);

-- ---------------------------------------------------------------------
-- 历史导入批次（演示异常页面，不关联真实文件）
-- ---------------------------------------------------------------------
INSERT INTO campus.import_batches
    (batch_code, source_filename, file_sha256, target_type, total_rows, valid_rows, invalid_rows,
     batch_status, created_by, created_at, finished_at)
VALUES
    ('DEMO-20260920-001', 'students_demo_20260920.xlsx',
     repeat('a', 64), 'students', 12, 10, 2, 'imported', 'demo.operator',
     TIMESTAMPTZ '2026-09-20 10:12:00+08', TIMESTAMPTZ '2026-09-20 10:13:41+08');

INSERT INTO campus.import_issues
    (batch_id, row_number, field_name, issue_code, severity, issue_message, issue_status)
SELECT b.id, v.row_number, v.field_name, v.issue_code, v.severity, v.msg, v.st
FROM campus.import_batches b
CROSS JOIN (VALUES
    (7,  '学号',   'DUPLICATE_STUDENT_NO', 'error',   '第 7 行学号与第 3 行重复',        'open'),
    (11, '入学年份', 'INVALID_ENUM',        'warning', '入学年份超出 1990-2100 合理范围', 'needs_review')
) AS v(row_number, field_name, issue_code, severity, msg, st)
WHERE b.batch_code = 'DEMO-20260920-001';

COMMIT;

-- 校验输出
SELECT 'students'      AS object, count(*) FROM campus.students       WHERE student_no LIKE 'DEMO%'
UNION ALL
SELECT 'student_changes', count(*) FROM campus.student_changes c
    JOIN campus.students s ON s.id = c.student_id WHERE s.student_no LIKE 'DEMO%'
UNION ALL
SELECT 'import_batches', count(*) FROM campus.import_batches WHERE batch_code LIKE 'DEMO-%'
UNION ALL
SELECT 'operation_logs', count(*) FROM campus.operation_logs;
