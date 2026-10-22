-- 内部请求认证：nonce 表与受控清理函数
-- 依赖：sql/001_schema.sql（campus schema）+ sql/003_roles.sql（campus_app 角色）
-- 执行：psql -v ON_ERROR_STOP=1 -f sql/004_internal_auth.sql（需具备建表与建角色权限）
-- 幂等：可重复执行
--
-- 回退：
--   DROP FUNCTION IF EXISTS campus.cleanup_internal_nonce();
--   DROP TABLE IF EXISTS campus.internal_nonce;
--   DROP ROLE IF EXISTS campus_nonce_cleaner;

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. nonce 表
--    campus_app 只有 SELECT / INSERT：不能删除任何 nonce（含自己刚写入的），
--    过期清理必须走下面的受控函数。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campus.internal_nonce (
    nonce      varchar(64)  PRIMARY KEY,
    seen_at    timestamptz  NOT NULL DEFAULT now(),
    expires_at timestamptz  NOT NULL DEFAULT now() + interval '24 hours'
);

COMMENT ON TABLE campus.internal_nonce IS
    '内部请求签名的一次性 nonce；由 Import API 写入，仅可经 cleanup_internal_nonce() 清理过期行';

CREATE INDEX IF NOT EXISTS idx_internal_nonce_expires
    ON campus.internal_nonce (expires_at);

REVOKE ALL ON campus.internal_nonce FROM PUBLIC;
GRANT SELECT, INSERT ON campus.internal_nonce TO campus_app;   -- 无 UPDATE / DELETE
REVOKE ALL ON campus.internal_nonce FROM campus_ro;

-- ---------------------------------------------------------------------------
-- 2. 专用清理属主：非登录、非超级用户，仅持有本表的 DELETE
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'campus_nonce_cleaner') THEN
        CREATE ROLE campus_nonce_cleaner NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA campus TO campus_nonce_cleaner;
GRANT SELECT, DELETE ON campus.internal_nonce TO campus_nonce_cleaner;  -- SELECT 用于评估 WHERE expires_at

-- ---------------------------------------------------------------------------
-- 3. 只删除已过期记录的函数（SECURITY DEFINER + 固定 search_path）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION campus.cleanup_internal_nonce()
    RETURNS integer
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = campus, pg_temp
AS $$
DECLARE
    removed integer;
BEGIN
    DELETE FROM campus.internal_nonce WHERE expires_at < now();
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END;
$$;

ALTER FUNCTION campus.cleanup_internal_nonce() OWNER TO campus_nonce_cleaner;

REVOKE ALL ON FUNCTION campus.cleanup_internal_nonce() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION campus.cleanup_internal_nonce() TO campus_app;

COMMIT;
