-- =====================================================================
-- 最小权限角色（不使用超级用户运行应用）
-- 执行前必须提供密码变量：
--   psql -v app_password='***' -v ro_password='***' -f sql/003_roles.sql
-- 说明：
--   1. campus_app  : Appsmith 与 Import API 使用；仅 SELECT/INSERT/UPDATE，无 DELETE
--   2. campus_ro   : 只读查看者使用；仅 SELECT
--   3. operation_logs 对 campus_app 仅授予 SELECT，禁止改写审计记录
-- =====================================================================

\set ON_ERROR_STOP on

-- 角色创建（幂等）
SELECT format('CREATE ROLE campus_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'campus_app')
\gexec

SELECT format('CREATE ROLE campus_ro LOGIN PASSWORD %L', :'ro_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'campus_ro')
\gexec

ALTER ROLE campus_app WITH PASSWORD :'app_password';
ALTER ROLE campus_ro  WITH PASSWORD :'ro_password';

ALTER ROLE campus_app SET search_path = campus, public;
ALTER ROLE campus_app SET statement_timeout = '30s';
ALTER ROLE campus_ro  SET search_path = campus, public;
ALTER ROLE campus_ro  SET statement_timeout = '30s';

-- 撤销默认的公共权限
REVOKE ALL ON SCHEMA campus FROM PUBLIC;

-- campus_app：业务读写
GRANT USAGE ON SCHEMA campus TO campus_app;
GRANT SELECT, INSERT, UPDATE ON
    campus.students,
    campus.student_changes,
    campus.import_batches,
    campus.import_issues
TO campus_app;
GRANT SELECT ON campus.operation_logs TO campus_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA campus TO campus_app;
GRANT SELECT ON campus.v_student_changes, campus.v_import_batch_summary TO campus_app;

-- campus_ro：只读
GRANT USAGE ON SCHEMA campus TO campus_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA campus TO campus_ro;

-- 显式收回（防止未来误加授权）
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA campus FROM campus_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON campus.operation_logs FROM campus_app;

-- 唯一例外：异常明细允许重新生成（重新校验时先清空本批次旧明细）
-- 业务主表（students / student_changes）仍然禁止物理删除，只允许逻辑停用。
GRANT DELETE ON campus.import_issues TO campus_app;

-- 验证输出
SELECT r.rolname,
       has_table_privilege(r.rolname, 'campus.students', 'INSERT') AS can_insert_student,
       has_table_privilege(r.rolname, 'campus.students', 'DELETE') AS can_delete_student,
       has_table_privilege(r.rolname, 'campus.operation_logs', 'UPDATE') AS can_update_log
FROM pg_roles r
WHERE r.rolname IN ('campus_app', 'campus_ro')
ORDER BY r.rolname;
