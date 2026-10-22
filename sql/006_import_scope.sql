-- =====================================================================
-- PR-C：导入批次归属、范围索引与批次/异常表审计
-- 目标库：campus（业务库）；正式库执行前必须先 pg_dump。
-- 可重复执行；回退语句见文件末尾。
-- =====================================================================
BEGIN;

-- 批次归属部门：由服务端从签名身份写入，客户端不可指定
ALTER TABLE campus.import_batches
    ADD COLUMN IF NOT EXISTS created_dept_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_batches_dept
    ON campus.import_batches (created_dept_id, created_at DESC);

-- 批次与异常表的行级审计：与业务写入同一事务；
-- actor 来自 campus.actor_user_id（受控后端注入），未注入时留空。
CREATE OR REPLACE FUNCTION campus.audit_import_stmt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = campus, pg_temp
AS $$
DECLARE
    v_actor     varchar(150);
    v_object_id varchar(80);
    v_before    jsonb;
    v_after     jsonb;
BEGIN
    v_actor := nullif(current_setting('campus.actor_user_id', true), '');
    v_object_id := COALESCE(NEW.id, OLD.id)::text;

    IF TG_OP = 'INSERT' THEN
        v_after := campus.audit_payload(to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        v_before := campus.audit_payload(to_jsonb(OLD));
        v_after := campus.audit_payload(to_jsonb(NEW));
    ELSE
        v_before := campus.audit_payload(to_jsonb(OLD));
    END IF;

    INSERT INTO campus.operation_logs (
        actor_user_id, actor_db_role, action, object_type, object_id,
        before_data, after_data, result
    ) VALUES (
        -- SECURITY DEFINER 下 current_user 是函数属主，必须用 session_user 记录连接角色
        v_actor, session_user, lower(TG_OP), TG_TABLE_NAME, v_object_id,
        v_before, v_after, 'success'
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_import_batches_audit ON campus.import_batches;
CREATE TRIGGER trg_import_batches_audit
    AFTER INSERT OR UPDATE OR DELETE ON campus.import_batches
    FOR EACH ROW EXECUTE FUNCTION campus.audit_import_stmt();

DROP TRIGGER IF EXISTS trg_import_issues_audit ON campus.import_issues;
CREATE TRIGGER trg_import_issues_audit
    AFTER INSERT OR UPDATE OR DELETE ON campus.import_issues
    FOR EACH ROW EXECUTE FUNCTION campus.audit_import_stmt();

COMMIT;

-- =====================================================================
-- 回退（人工执行，先确认无并发写入）
-- DROP TRIGGER IF EXISTS trg_import_issues_audit ON campus.import_issues;
-- DROP TRIGGER IF EXISTS trg_import_batches_audit ON campus.import_batches;
-- DROP FUNCTION IF EXISTS campus.audit_import_stmt();
-- DROP INDEX IF EXISTS campus.idx_batches_dept;
-- ALTER TABLE campus.import_batches DROP COLUMN IF EXISTS created_dept_id;
-- =====================================================================
