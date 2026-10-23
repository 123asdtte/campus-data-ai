-- =====================================================================
-- AI 校园助手原型：隔离库结构与虚构数据
--
-- 重要：
--   1. 本脚本只用于隔离 POC 数据库（campus_ai_poc），不连接、不写入主业务库；
--   2. 所有姓名、学号、手机号、邮箱均为虚构，仅用于演示与测试；
--   3. 每次执行会 DROP SCHEMA ai，得到可复现的干净状态（POC 专属，禁止用于正式库）；
--   4. 执行需提供密码变量：
--        psql -v ai_ro_password=... -v ai_audit_password=... -f 001_schema.sql
-- =====================================================================

\set ON_ERROR_STOP on

-- 硬保护：禁止对非 POC 库执行（会 DROP SCHEMA）
DO $$
BEGIN
    IF current_database() <> 'campus_ai_poc' THEN
        RAISE EXCEPTION '本脚本仅允许在 campus_ai_poc 执行，当前数据库：%', current_database();
    END IF;
END
$$;

DROP SCHEMA IF EXISTS ai CASCADE;
DROP ROLE IF EXISTS ai_ro;
DROP ROLE IF EXISTS ai_audit_writer;

CREATE SCHEMA ai;

-- ---------------------------------------------------------------------
-- 1. 角色：读账号只能 SELECT；审计写入账号只能 INSERT 审计表
-- ---------------------------------------------------------------------
SELECT format('CREATE ROLE ai_ro LOGIN PASSWORD %L', :'ai_ro_password') \gexec
SELECT format('CREATE ROLE ai_audit_writer LOGIN PASSWORD %L', :'ai_audit_password') \gexec

ALTER ROLE ai_ro SET search_path = ai, public;
ALTER ROLE ai_ro SET statement_timeout = '10s';
ALTER ROLE ai_audit_writer SET search_path = ai, public;
ALTER ROLE ai_audit_writer SET statement_timeout = '10s';

REVOKE ALL ON SCHEMA ai FROM PUBLIC;
GRANT USAGE ON SCHEMA ai TO ai_ro, ai_audit_writer;

-- ---------------------------------------------------------------------
-- 2. 业务表（全部为虚构数据）
-- ---------------------------------------------------------------------
CREATE TABLE ai.colleges (
    code varchar(16) PRIMARY KEY,
    name varchar(64) NOT NULL
);

CREATE TABLE ai.students (
    student_no  varchar(32) PRIMARY KEY,
    name        varchar(64) NOT NULL,
    college_code varchar(16) NOT NULL REFERENCES ai.colleges(code),
    major       varchar(64) NOT NULL,
    class_name  varchar(64) NOT NULL,
    enroll_year integer NOT NULL,
    status      varchar(16) NOT NULL,   -- 在校 / 休学 / 退学
    phone       varchar(32),
    email       varchar(128)
);

CREATE TABLE ai.import_batches (
    id           bigserial PRIMARY KEY,
    batch_code   varchar(32) NOT NULL,
    college_code varchar(16) NOT NULL REFERENCES ai.colleges(code),
    target_type  varchar(32) NOT NULL,
    total_rows   integer NOT NULL,
    valid_rows   integer NOT NULL,
    invalid_rows integer NOT NULL,
    status        varchar(16) NOT NULL,  -- imported / validated / failed
    created_at   timestamptz NOT NULL
);

CREATE TABLE ai.import_issues (
    id         bigserial PRIMARY KEY,
    batch_id   bigint NOT NULL REFERENCES ai.import_batches(id),
    issue_code varchar(64) NOT NULL,
    severity   varchar(16) NOT NULL,
    count      integer NOT NULL
);

CREATE TABLE ai.users (
    username     varchar(64) PRIMARY KEY,
    display_name varchar(64) NOT NULL,
    role         varchar(32) NOT NULL,   -- admin / college_viewer / readonly
    college_code varchar(16) REFERENCES ai.colleges(code)  -- admin 为 NULL
);

CREATE TABLE ai.audit (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    requester  varchar(64) NOT NULL,
    role       varchar(32) NOT NULL,
    college    varchar(16),
    question   text NOT NULL,
    intent     varchar(32) NOT NULL,
    status     varchar(16) NOT NULL,     -- ok / denied / unknown / error
    row_count  integer NOT NULL DEFAULT 0,
    detail     jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------
-- 3. 授权（最小权限）
-- ---------------------------------------------------------------------
GRANT SELECT ON ai.colleges, ai.students, ai.import_batches, ai.import_issues, ai.users TO ai_ro;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ai TO ai_ro;

GRANT INSERT ON ai.audit TO ai_audit_writer;
GRANT USAGE, SELECT ON SEQUENCE ai.audit_id_seq TO ai_audit_writer;

-- 显式收回：读账号不得写，审计账号不得读业务表
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ai.colleges, ai.students, ai.import_batches,
    ai.import_issues, ai.users FROM ai_ro;
REVOKE SELECT ON ai.colleges, ai.students, ai.import_batches, ai.import_issues, ai.users
    FROM ai_audit_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON ai.audit FROM ai_audit_writer;

-- ---------------------------------------------------------------------
-- 4. 虚构数据
-- ---------------------------------------------------------------------
INSERT INTO ai.colleges (code, name) VALUES
    ('CS', '计算机学院'),
    ('EE', '电子信息学院'),
    ('FL', '外国语学院');

INSERT INTO ai.users (username, display_name, role, college_code) VALUES
    ('ai_admin',    '演示管理员',   'admin',          NULL),
    ('ai_cs',       '计算机学院老师', 'college_viewer', 'CS'),
    ('ai_ee',       '电信学院老师',  'college_viewer', 'EE'),
    ('ai_ro',       '只读观察员',   'readonly',       'FL');

-- 120 名虚构学生：3 个学院轮流分配；每 12 人 1 人休学；部分缺手机号/邮箱
INSERT INTO ai.students (student_no, name, college_code, major, class_name, enroll_year, status, phone, email)
SELECT
    'AIC2026' || lpad(i::text, 4, '0'),
    '测试学生' || lpad(i::text, 3, '0'),
    CASE i % 3 WHEN 0 THEN 'CS' WHEN 1 THEN 'EE' ELSE 'FL' END,
    CASE i % 3 WHEN 0 THEN '软件技术' WHEN 1 THEN '物联网应用技术' ELSE '商务英语' END,
    '演示班' || lpad(((i - 1) / 20 + 1)::text, 2, '0'),
    2026,
    CASE WHEN i % 12 = 0 THEN '休学' WHEN i % 37 = 0 THEN '退学' ELSE '在校' END,
    CASE WHEN i % 5 = 0 THEN NULL ELSE '1380000' || lpad(i::text, 4, '0') END,
    CASE WHEN i % 6 = 0 THEN NULL ELSE 'student' || i::text || '@example.test' END
FROM generate_series(1, 120) AS i;

-- 8 个虚构导入批次：3 个失败、5 个成功；学院轮流分配
INSERT INTO ai.import_batches (batch_code, college_code, target_type, total_rows, valid_rows, invalid_rows, status, created_at)
SELECT
    'AIB202610' || lpad(i::text, 2, '0'),
    CASE i % 3 WHEN 0 THEN 'CS' WHEN 1 THEN 'EE' ELSE 'FL' END,
    CASE WHEN i % 2 = 0 THEN 'students' ELSE 'student_changes' END,
    100, CASE WHEN i % 4 = 0 THEN 0 ELSE 90 + i % 10 END,
    CASE WHEN i % 4 = 0 THEN 100 ELSE 10 - i % 10 END,
    CASE WHEN i % 4 = 0 THEN 'failed' ELSE 'imported' END,
    now() - (i || ' days')::interval
FROM generate_series(1, 8) AS i;

-- 异常分布：失败批次以格式错误为主，成功批次以重复学号为主
INSERT INTO ai.import_issues (batch_id, issue_code, severity, count)
SELECT
    b.id,
    CASE WHEN b.status = 'failed' THEN 'INVALID_FORMAT' ELSE 'DUPLICATE_STUDENT_NO' END,
    'error',
    CASE WHEN b.status = 'failed' THEN 100 ELSE 5 END
FROM ai.import_batches b;

-- ---------------------------------------------------------------------
-- 5. 验证输出（不打印任何密码）
-- ---------------------------------------------------------------------
SELECT r.rolname,
       has_schema_privilege(r.rolname, 'ai', 'USAGE') AS can_use_schema,
       has_table_privilege(r.rolname, 'ai.students', 'SELECT') AS can_read_students,
       has_table_privilege(r.rolname, 'ai.students', 'INSERT') AS can_write_students,
       has_table_privilege(r.rolname, 'ai.audit', 'INSERT') AS can_append_audit
FROM pg_roles r
WHERE r.rolname IN ('ai_ro', 'ai_audit_writer')
ORDER BY r.rolname;
