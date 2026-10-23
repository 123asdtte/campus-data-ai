-- Local demo accounts for the role-based student portal.
-- Local only. Password for all demo accounts: Demo@2026
-- Apply to the campus_gateway database:
--   docker exec -i campus-gateway-db psql -U gateway_dba -d campus_gateway \
--     -v ON_ERROR_STOP=1 < scripts/demo/seed-demo-accounts.sql
--
-- Roles:
--   student_portal : student, data scope = self (see own schedule only)
--   xgb            : 学工处, data scope = all (change ledger / reports)
--   counselor      : 辅导员, data scope = self/assigned classes (demo UI filters by nickname)
--
-- This is a local demo seed. Production accounts must be provisioned through
-- HR/student registry and must not reuse this shared password.

insert into sys_role values
  (1761300000000000101, '学生课表查询', 'student_portal', 10, '5', 't', 't', '0', '0', 1761000000000000103, 1761100000000000001, now(), null, null, 'local demo: student schedule only'),
  (1761300000000000102, '学工处（演示）', 'xgb', 11, '1', 't', 't', '0', '0', 1761000000000000103, 1761100000000000001, now(), null, null, 'local demo: student affairs'),
  (1761300000000000103, '辅导员（演示）', 'counselor', 12, '5', 't', 't', '0', '0', 1761000000000000103, 1761100000000000001, now(), null, null, 'local demo: counselor')
on conflict (role_id) do nothing;

insert into sys_user values
  (1761100000000000301, 1761000000000000103, 'SK-2026-000001', '万*', 'sys_user', '', '', '0', null,
   '$2a$10$ZhFKK2LIcIVeng/ayM951udpb2wTnk3otMdJv//spn42x3qRKS58q', '0', '0', '', null,
   1761000000000000103, 1761100000000000001, now(), null, null, 'local demo student'),
  (1761100000000000302, 1761000000000000103, 'xgb01', '张老师', 'sys_user', '', '', '0', null,
   '$2a$10$ZhFKK2LIcIVeng/ayM951udpb2wTnk3otMdJv//spn42x3qRKS58q', '0', '0', '', null,
   1761000000000000103, 1761100000000000001, now(), null, null, 'local demo student affairs'),
  (1761100000000000303, 1761000000000000103, 'counselor01', '戴雅琴', 'sys_user', '', '', '0', null,
   '$2a$10$ZhFKK2LIcIVeng/ayM951udpb2wTnk3otMdJv//spn42x3qRKS58q', '0', '0', '', null,
   1761000000000000103, 1761100000000000001, now(), null, null, 'local demo counselor')
on conflict (user_id) do nothing;

insert into sys_user_role values
  (1761100000000000301, 1761300000000000101),
  (1761100000000000302, 1761300000000000102),
  (1761100000000000303, 1761300000000000103)
on conflict do nothing;
