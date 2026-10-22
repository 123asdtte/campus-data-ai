-- =====================================================================
-- PR-C：导入批次归属、范围索引与导入审计（方案 C）
-- 目标库：campus（业务库）；正式库执行前必须先 pg_dump。
-- 可重复执行；回退语句见文件末尾。
--
-- 审计设计依据 docs/IMPORT-AUDIT-DESIGN.md（Issue #10）：
--   1. import_batches：行级触发器，记录每次状态跃迁（每批次仅 4~5 行）；
--   2. import_issues：不做逐行审计（一次校验最多 2N 行噪声），
--      改为在删除/重写时写一条 JSON 摘要；
--   3. 收回 campus_app 对 import_issues 的 DELETE，删除只能经受控函数，
--      保证「删之前必须留痕」由数据库强制。
-- =====================================================================
BEGIN;

-- 批次归属部门：由服务端从签名身份写入，客户端不可指定
ALTER TABLE campus.import_batches
    ADD COLUMN IF NOT EXISTS created_dept_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_batches_dept
    ON campus.import_batches (created_dept_id, created_at DESC);

-- ---------------------------------------------------------------------
-- 1. 批次行级审计：与业务写入同一事务；actor 来自 campus.actor_user_id
-- ---------------------------------------------------------------------
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

-- 旧的逐行异常审计触发器必须移除（方案 A 的噪声来源）
DROP TRIGGER IF EXISTS trg_import_issues_audit ON campus.import_issues;

-- ---------------------------------------------------------------------
-- 2. 异常明细：删除收口 + 摘要
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION campus.clear_import_issues(p_batch_id bigint, p_trigger text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = campus, pg_temp
AS $$
DECLARE
    v_actor     varchar(150);
    v_deleted   integer;
    v_by_code   jsonb;
    v_by_sev    jsonb;
BEGIN
    v_actor := nullif(current_setting('campus.actor_user_id', true), '');

    -- 删前留痕：按 code/severity 汇总旧明细
    SELECT COALESCE(jsonb_object_agg(issue_code, cnt), '{}'::jsonb)
      INTO v_by_code
      FROM (SELECT issue_code, count(*) AS cnt
              FROM campus.import_issues WHERE batch_id = p_batch_id
             GROUP BY issue_code) s;

    SELECT COALESCE(jsonb_object_agg(severity, cnt), '{}'::jsonb)
      INTO v_by_sev
      FROM (SELECT severity, count(*) AS cnt
              FROM campus.import_issues WHERE batch_id = p_batch_id
             GROUP BY severity) s;

    DELETE FROM campus.import_issues WHERE batch_id = p_batch_id;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    IF v_deleted > 0 THEN
        INSERT INTO campus.operation_logs (
            actor_user_id, actor_db_role, action, object_type, object_id, details, result
        ) VALUES (
            v_actor, session_user, 'delete', 'import_issues', p_batch_id::text,
            jsonb_build_object(
                'batch_id', p_batch_id, 'trigger', p_trigger,
                'deleted', v_deleted, 'by_code', v_by_code, 'by_severity', v_by_sev
            ),
            'success'
        );
    END IF;

    RETURN v_deleted;
END;
$$;

CREATE OR REPLACE FUNCTION campus.record_import_issues(p_batch_id bigint, p_trigger text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = campus, pg_temp
AS $$
DECLARE
    v_actor   varchar(150);
    v_total   integer;
    v_by_code jsonb;
    v_by_sev  jsonb;
BEGIN
    v_actor := nullif(current_setting('campus.actor_user_id', true), '');

    SELECT count(*)::integer INTO v_total
      FROM campus.import_issues WHERE batch_id = p_batch_id;

    SELECT COALESCE(jsonb_object_agg(issue_code, cnt), '{}'::jsonb)
      INTO v_by_code
      FROM (SELECT issue_code, count(*) AS cnt
              FROM campus.import_issues WHERE batch_id = p_batch_id
             GROUP BY issue_code) s;

    SELECT COALESCE(jsonb_object_agg(severity, cnt), '{}'::jsonb)
      INTO v_by_sev
      FROM (SELECT severity, count(*) AS cnt
              FROM campus.import_issues WHERE batch_id = p_batch_id
             GROUP BY severity) s;

    -- 每次重写写一条摘要（即使 0 条也记录“校验跑过且无异常”）
    INSERT INTO campus.operation_logs (
        actor_user_id, actor_db_role, action, object_type, object_id, details, result
    ) VALUES (
        v_actor, session_user, 'insert', 'import_issues', p_batch_id::text,
        jsonb_build_object(
            'batch_id', p_batch_id, 'trigger', p_trigger,
            'rows', v_total, 'by_code', v_by_code, 'by_severity', v_by_sev
        ),
        'success'
    );

    RETURN v_total;
END;
$$;

-- 删除收口：应用账号不再拥有 import_issues 的 DELETE
REVOKE DELETE ON campus.import_issues FROM campus_app;
GRANT EXECUTE ON FUNCTION campus.clear_import_issues(bigint, text) TO campus_app;
GRANT EXECUTE ON FUNCTION campus.record_import_issues(bigint, text) TO campus_app;

COMMIT;

-- =====================================================================
-- 回退（人工执行，先确认无并发写入）
-- DROP TRIGGER IF EXISTS trg_import_batches_audit ON campus.import_batches;
-- DROP FUNCTION IF EXISTS campus.audit_import_stmt();
-- DROP FUNCTION IF EXISTS campus.record_import_issues(bigint, text);
-- DROP FUNCTION IF EXISTS campus.clear_import_issues(bigint, text);
-- DROP INDEX IF EXISTS campus.idx_batches_dept;
-- ALTER TABLE campus.import_batches DROP COLUMN IF EXISTS created_dept_id;
-- GRANT DELETE ON campus.import_issues TO campus_app;  -- 恢复 003 的唯一例外
-- =====================================================================
