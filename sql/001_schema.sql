-- =====================================================================
-- 校园数据管理与 AI 助手平台 — 一期数据库结构
-- 目标数据库：PostgreSQL 16
-- 执行方式：psql -v ON_ERROR_STOP=1 -f sql/001_schema.sql
-- 说明：
--   1. 业务对象统一放在 campus schema，避免与 Appsmith 自身元数据混用。
--   2. 不采集身份证号、手机号、住址等敏感字段（最小必要原则）。
--   3. 所有删除均为逻辑停用（is_active=false），不提供物理删除授权。
-- =====================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS campus;
SET search_path TO campus, public;

-- ---------------------------------------------------------------------
-- 通用函数
-- ---------------------------------------------------------------------

-- updated_at 自动维护
CREATE OR REPLACE FUNCTION campus.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- 审计载荷：剔除敏感字段，避免历史记录复制敏感数据
CREATE OR REPLACE FUNCTION campus.audit_payload(p_row jsonb)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
AS $$
    -- 若未来新增敏感列，只需把列名加入下面的数组
    SELECT p_row - ARRAY['id_card_no', 'phone_no', 'home_address', 'family_info']::text[];
$$;

-- 行级审计触发器：与业务写入处于同一事务，不依赖前端额外 INSERT
CREATE OR REPLACE FUNCTION campus.audit_row()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = campus, pg_temp
AS $$
DECLARE
    v_action        text;
    v_actor_user_id varchar(150);
    v_before        jsonb;
    v_after         jsonb;
    v_changed       text[];
    v_object_id     varchar(80);
BEGIN
    -- 操作人身份来自同一事务内设置的会话变量（受控后端负责注入）
    -- 未注入时退化为数据库账号，测试阶段可接受，正式阶段不可接受
    v_actor_user_id := nullif(current_setting('campus.actor_user_id', true), '');

    IF TG_OP = 'INSERT' THEN
        v_action := 'insert';
        v_after  := campus.audit_payload(to_jsonb(NEW));
        v_object_id := NEW.id::text;
    ELSIF TG_OP = 'UPDATE' THEN
        v_action := 'update';
        v_before := campus.audit_payload(to_jsonb(OLD));
        v_after  := campus.audit_payload(to_jsonb(NEW));
        v_object_id := NEW.id::text;

        -- 无实质变化则不留痕（updated_at 由触发器赋值，需排除）
        IF (v_before - 'updated_at') = (v_after - 'updated_at') THEN
            RETURN NEW;
        END IF;

        SELECT array_agg(k ORDER BY k) INTO v_changed
        FROM jsonb_object_keys(v_after) AS k
        WHERE (v_before -> k) IS DISTINCT FROM (v_after -> k)
          AND k <> 'updated_at';
    ELSE
        v_action := 'delete';
        v_before := campus.audit_payload(to_jsonb(OLD));
        v_object_id := OLD.id::text;
    END IF;

    INSERT INTO campus.operation_logs (
        actor_user_id, actor_db_role, action, object_type, object_id,
        changed_fields, before_data, after_data, result
    ) VALUES (
        -- SECURITY DEFINER 下 current_user 会变成函数属主，必须用 session_user 记录真实登录角色
        v_actor_user_id, session_user, v_action, TG_TABLE_NAME, v_object_id,
        v_changed, v_before, v_after, 'success'
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- ---------------------------------------------------------------------
-- 学生信息
-- ---------------------------------------------------------------------
CREATE TABLE campus.students (
    id               BIGSERIAL PRIMARY KEY,
    student_no       VARCHAR(32)  NOT NULL,
    student_name     VARCHAR(100) NOT NULL,
    college_name     VARCHAR(100),
    major_name       VARCHAR(100),
    class_name       VARCHAR(100),
    enrollment_year  SMALLINT,
    student_status   VARCHAR(20)  NOT NULL DEFAULT 'enrolled',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT students_student_no_key UNIQUE (student_no),
    CONSTRAINT students_student_no_format CHECK (student_no = btrim(student_no) AND student_no <> ''),
    CONSTRAINT students_name_not_blank    CHECK (btrim(student_name) <> ''),
    CONSTRAINT students_year_range        CHECK (enrollment_year IS NULL OR enrollment_year BETWEEN 1990 AND 2100),
    CONSTRAINT students_status_enum       CHECK (student_status IN ('enrolled', 'suspended', 'withdrawn', 'graduated', 'other'))
);

COMMENT ON TABLE  campus.students IS '学生基本信息（最小必要字段，不含身份证号/联系方式）';
COMMENT ON COLUMN campus.students.student_status IS 'enrolled=在校 suspended=休学 withdrawn=退学 graduated=毕业 other=其他';

CREATE INDEX idx_students_class   ON campus.students (class_name) WHERE is_active;
CREATE INDEX idx_students_college ON campus.students (college_name) WHERE is_active;

-- ---------------------------------------------------------------------
-- 学籍异动
-- ---------------------------------------------------------------------
CREATE TABLE campus.student_changes (
    id                BIGSERIAL PRIMARY KEY,
    student_id        BIGINT       NOT NULL,
    change_type       VARCHAR(30)  NOT NULL,
    effective_date    DATE         NOT NULL,
    change_reason     VARCHAR(500),
    record_status     VARCHAR(20)  NOT NULL DEFAULT 'draft',
    source_batch_id   BIGINT,
    source_row_number INTEGER,
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT student_changes_student_fk FOREIGN KEY (student_id) REFERENCES campus.students (id),
    CONSTRAINT student_changes_type_enum CHECK (change_type IN ('suspend', 'resume', 'withdraw', 'transfer_major', 'transfer_school', 'retain', 'other')),
    CONSTRAINT student_changes_status_enum CHECK (record_status IN ('draft', 'pending_review', 'confirmed', 'returned')),
    CONSTRAINT student_changes_date_sane CHECK (effective_date BETWEEN DATE '1990-01-01' AND DATE '2100-12-31')
);

COMMENT ON TABLE campus.student_changes IS '学籍异动记录；record_status 仅表示本工具内的整理状态，不等同学校正式审批';
COMMENT ON COLUMN campus.student_changes.change_type IS 'suspend=休学 resume=复学 withdraw=退学 transfer_major=转专业 transfer_school=转学 retain=保留学籍 other=其他';

CREATE INDEX idx_changes_student     ON campus.student_changes (student_id);
CREATE INDEX idx_changes_date        ON campus.student_changes (effective_date);
CREATE INDEX idx_changes_type_status ON campus.student_changes (change_type, record_status) WHERE is_active;

-- ---------------------------------------------------------------------
-- 导入批次
-- ---------------------------------------------------------------------
CREATE TABLE campus.import_batches (
    id             BIGSERIAL PRIMARY KEY,
    batch_code     VARCHAR(40)  NOT NULL,
    source_filename VARCHAR(255) NOT NULL,
    file_sha256    CHAR(64)     NOT NULL,
    target_type    VARCHAR(30)  NOT NULL,
    total_rows     INTEGER      NOT NULL DEFAULT 0,
    valid_rows     INTEGER      NOT NULL DEFAULT 0,
    invalid_rows   INTEGER      NOT NULL DEFAULT 0,
    batch_status   VARCHAR(20)  NOT NULL DEFAULT 'uploaded',
    staged_path    VARCHAR(255),
    failure_reason VARCHAR(500),
    created_by     VARCHAR(150),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,

    CONSTRAINT import_batches_code_key UNIQUE (batch_code),
    CONSTRAINT import_batches_target_enum CHECK (target_type IN ('students', 'student_changes')),
    CONSTRAINT import_batches_status_enum CHECK (batch_status IN ('uploaded', 'validated', 'imported', 'failed')),
    CONSTRAINT import_batches_row_math CHECK (total_rows >= 0 AND valid_rows >= 0 AND invalid_rows >= 0
                                              AND valid_rows + invalid_rows <= total_rows)
);

CREATE INDEX idx_batches_hash   ON campus.import_batches (file_sha256);
CREATE INDEX idx_batches_status ON campus.import_batches (batch_status, created_at DESC);

-- ---------------------------------------------------------------------
-- 导入异常
-- ---------------------------------------------------------------------
CREATE TABLE campus.import_issues (
    id            BIGSERIAL PRIMARY KEY,
    batch_id      BIGINT       NOT NULL,
    row_number    INTEGER      NOT NULL,
    field_name    VARCHAR(100),
    issue_code    VARCHAR(50)  NOT NULL,
    severity      VARCHAR(20)  NOT NULL DEFAULT 'error',
    issue_message VARCHAR(500) NOT NULL,
    issue_status  VARCHAR(20)  NOT NULL DEFAULT 'open',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT import_issues_batch_fk FOREIGN KEY (batch_id) REFERENCES campus.import_batches (id) ON DELETE CASCADE,
    CONSTRAINT import_issues_code_enum CHECK (issue_code IN (
        'MISSING_REQUIRED', 'DUPLICATE_STUDENT_NO', 'UNKNOWN_STUDENT', 'INVALID_DATE',
        'INVALID_ENUM', 'DUPLICATE_BATCH', 'COLUMN_MAPPING_REQUIRED', 'VALUE_TOO_LONG'
    )),
    CONSTRAINT import_issues_severity_enum CHECK (severity IN ('error', 'warning')),
    CONSTRAINT import_issues_status_enum   CHECK (issue_status IN ('open', 'resolved', 'needs_review')),
    CONSTRAINT import_issues_row_positive  CHECK (row_number >= 1)
);

CREATE INDEX idx_issues_batch  ON campus.import_issues (batch_id);
CREATE INDEX idx_issues_status ON campus.import_issues (issue_status, severity);

-- ---------------------------------------------------------------------
-- 操作记录（审计）
-- ---------------------------------------------------------------------
CREATE TABLE campus.operation_logs (
    id             BIGSERIAL PRIMARY KEY,
    actor_user_id  VARCHAR(150),
    actor_db_role  VARCHAR(63) NOT NULL,
    action         VARCHAR(10) NOT NULL,
    object_type    VARCHAR(50) NOT NULL,
    object_id      VARCHAR(80),
    changed_fields TEXT[],
    before_data    JSONB,
    after_data     JSONB,
    result         VARCHAR(10) NOT NULL DEFAULT 'success',
    details        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT operation_logs_action_enum CHECK (action IN ('insert', 'update', 'delete')),
    CONSTRAINT operation_logs_result_enum CHECK (result IN ('success', 'failed'))
);

COMMENT ON TABLE  campus.operation_logs IS '业务变更审计；由触发器在同一事务写入，不可由应用侧更新或删除';
COMMENT ON COLUMN campus.operation_logs.actor_user_id IS '可信操作人标识；由受控后端在同一事务内通过 set_config(campus.actor_user_id) 注入，为空表示仅能识别数据库账号';

CREATE INDEX idx_logs_created ON campus.operation_logs (created_at DESC);
CREATE INDEX idx_logs_object  ON campus.operation_logs (object_type, object_id);

-- ---------------------------------------------------------------------
-- 触发器
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_students_updated_at
    BEFORE UPDATE ON campus.students
    FOR EACH ROW EXECUTE FUNCTION campus.set_updated_at();

CREATE TRIGGER trg_students_audit
    AFTER INSERT OR UPDATE OR DELETE ON campus.students
    FOR EACH ROW EXECUTE FUNCTION campus.audit_row();

CREATE TRIGGER trg_changes_updated_at
    BEFORE UPDATE ON campus.student_changes
    FOR EACH ROW EXECUTE FUNCTION campus.set_updated_at();

CREATE TRIGGER trg_changes_audit
    AFTER INSERT OR UPDATE OR DELETE ON campus.student_changes
    FOR EACH ROW EXECUTE FUNCTION campus.audit_row();

-- ---------------------------------------------------------------------
-- 便于页面使用的只读视图
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW campus.v_student_changes AS
SELECT c.id,
       c.student_id,
       s.student_no,
       s.student_name,
       s.college_name,
       s.class_name,
       c.change_type,
       c.effective_date,
       c.change_reason,
       c.record_status,
       c.source_batch_id,
       c.is_active,
       c.created_at,
       c.updated_at
FROM campus.student_changes c
JOIN campus.students s ON s.id = c.student_id;

CREATE OR REPLACE VIEW campus.v_import_batch_summary AS
SELECT b.id,
       b.batch_code,
       b.source_filename,
       b.target_type,
       b.total_rows,
       b.valid_rows,
       b.invalid_rows,
       b.batch_status,
       b.created_by,
       b.created_at,
       b.finished_at,
       COALESCE(i.error_count, 0)   AS error_count,
       COALESCE(i.warning_count, 0) AS warning_count
FROM campus.import_batches b
LEFT JOIN (
    SELECT batch_id,
           count(*) FILTER (WHERE severity = 'error')   AS error_count,
           count(*) FILTER (WHERE severity = 'warning') AS warning_count
    FROM campus.import_issues
    GROUP BY batch_id
) i ON i.batch_id = b.id;

COMMIT;
