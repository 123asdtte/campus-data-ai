# PR #16 合并前安全审查（作者侧复核）

- **对象**：`campus-data-ai` PR #16，head `e324091`
- **审查方式**：代码逐行 + 独立测试库探针；**非第三方独立审查**（作者自查，结论需你复核）
- **结论**：**初始 REQUEST CHANGES → 修复后 PASS（附 2 项未验证）**

---

## 1. 第一优先级：`PUT /students/{no}`

### 1.1 代码证据（满足三层校验）

| 检查项 | 结论 | 证据 |
|---|---|---|
| 强制验签 | ✅ | `routes/students.py:72` `current: Optional[Who] = Depends(identity)`；开启态 `identity = require_internal` |
| 强制写权限 | ✅ | `:75` `require_perm(current, "student:write")` |
| 学院范围由服务端强制 | ✅ | `:84` `forced_college=require_college(current)` → `queries.py:165-167` 进入 SQL `WHERE college_name = %s` |
| 不能靠客户端参数扩大范围 | ✅ | 学院取自签名声明；请求体模型 `StudentUpdate` 无 `college_name` 字段 |
| 审计操作人可信 | ✅ | `queries.py:172` `set_config` 与 UPDATE 同事务；actor 来自 `resolve_actor(current, x_actor)` |

### 1.2 审查发现

**P1（证据缺口，非代码缺陷）：开启态零测试**

- 审查时全仓只有 `test_auth_disabled.py:22-38` 的"关闭态 405"用例；
- `test_internal_auth.py`、`test_route_matrix.py` 的 11 条路由清单**均未包含 PUT**；
- 结论："只在开启时注册"成立，但"注册后是否真的要求认证/权限/范围"当时**没有测试证据**——你的判断正确。

**处理**：新增 `tests/test_student_write.py`（9 项），逐条覆盖：

| 场景 | 断言 | 结果 |
|---|---|---|
| 未签名 | 401 | PASS |
| 有签名但缺 `student:write` | 403 | PASS |
| 跨学院目标学生 | 403 + 学生/审计快照不变 | PASS |
| 合法请求 | 200、DB 已改、`actor_user_id=ry:college_a`、`changed_fields` 含字段 | PASS |
| 伪造 `X-Actor` | 审计仍为 `ry:college_a` | PASS |
| 不存在学生 | 404 | PASS |
| 空请求体 | 400 | PASS |

**P2（真实缺陷，已修）：空白/`null` 姓名导致 500**

- 复现：`PUT {"student_name":"   "}` → `CheckViolation`；`{"student_name": null}` → `NotNullViolation`；
- 原因：`queries.update_student` 未做非空校验，psycopg 异常未被 `ServiceError` 映射；
- 修复：`queries.py:146-150` 增加 `student_name` 去空白校验 → 422；
- 复测：两项均返回 4xx，`test_student_write.py::test_非法姓名返回4xx而非500` 通过。

### 1.3 是否应移至 PR-B？

**建议保留在 PR-A**：路由在关闭态不注册、开启态有完整三层校验与 9 项测试，且 `student:write` 权限点已在 POC 验证过；移至 PR-B 反而会让"PR-A 覆盖全部路由"的目标出现缺口。前提是上述测试随 PR 合并。

---

## 2. 第二优先级：数据库安全边界（`sql/004`）

| 检查项 | 结论 | 证据 |
|---|---|---|
| `campus_app` 不能直接删 nonce | ✅ | `sql/004:31` 仅 `SELECT, INSERT`；测试 `campus_app` 直删 → `InsufficientPrivilege` |
| 清理函数属主专用、NOLOGIN | ✅ | `:40` `CREATE ROLE ... NOLOGIN`；运行时 `pg_roles.rolcanlogin=false` 断言 |
| 固定 `search_path` | ✅ | `:55` `SET search_path = campus, pg_temp` |
| 仅删过期记录 | ✅ | 函数体 `WHERE expires_at < now()`；测试插入 1 过期 + 1 未过期，返回 1 且未过期仍在 |
| PUBLIC 不可执行 | ✅ | `:68` `REVOKE ALL ... FROM PUBLIC`；`proacl` 无 `=X/` 断言 |
| 属主不能触达业务表 | ✅ | `campus_nonce_cleaner` 对 `students`/`operation_logs`/`import_batches` 的 SELECT/DELETE/INSERT/UPDATE 均为 false |

> 审查中修正过一个实际配置：`DELETE ... WHERE expires_at < now()` 除了 DELETE 还需要对该列的 **SELECT**（PostgreSQL 评估谓词），最初只授 DELETE 导致清理函数运行时报 `permission denied`；已在 `:46` 补 `SELECT`。

---

## 3. 第三优先级：认证边界与旧行为

| 检查项 | 结论 |
|---|---|
| 11 条业务路由开启态全部验签 + 权限 | ✅ 矩阵 34 项（无签名 401 / 缺权限 403 / 管理员限制 / 范围 / 副作用） |
| 非管理员导入请求被拒 | ✅ 7 条参数化 403（持全部 `import:batch:*` 仍拒） |
| 学院过滤由服务端控制 | ✅ 列表 SQL 交集（越界 `college` → total=0）、详情 403 |
| `/health` 仅 `{"status":"ok"}` | ✅ `routes/health.py`；`test_auth_disabled.py` 断言字段集合 |
| `/health/ready` 不泄露细节 | ✅ 503 固定文案 `database unavailable`；原 2 处断言已改打 readiness |
| 关闭态旧行为回归 | ✅ 130 passed（112 原有 + 新增关闭态） |
| CI 管理/业务连接分离 | ✅ 初始化与管理清理用 `CAMPUS_TEST_ADMIN_DATABASE_URL`，业务测试 DSN 指向 `campus_app`；缺管理 DSN 时 14 项 ERROR |

---

## 4. 修复后测试结果

| 套件 | 结果 |
|---|---|
| 开启态（auth + matrix + PUT + 权限） | **97 passed** |
| 关闭态全量 | **130 passed, 0 failed**（82 项按模式 skip，1 xfail） |
| 全新库初始化 + 权限校验 | **11/11 PASS** |

本次新增测试：`test_student_write.py`（9）、`test_db_privileges.py` 追加 2 项属主/ACL 断言。

---

## 5. 未验证项（不得视为通过）

1. **PUT 的并发写**：两个管理员同时改同一学生，未做竞态测试（当前依赖行级锁，行为未取证）。
2. **PUT 的审计变更差异**：`changed_fields` 由应用层写入，未验证"新旧值对比"是否完整（触发器只记录字段名）。
3. 大文件内存、nonce 表增长、审计批量性能：仍属 P2，留 PR-E。
4. Java 网关未实现，跨语言 canonical 只用金标向量固定，**未做真实联调**。

---

## 6. 结论

- 审查时：**REQUEST CHANGES**（PUT 开启态零测试；空姓名 500）；
- 两项均已修复并有实测证据，**当前建议 PASS（仅限 PR-A 合并）**；
- 合并后仍必须保持 `INTERNAL_AUTH_ENABLED=false`，直至 PR-C/D/E 完成；
- 本报告是**作者自查**，你需要独立复核 `tests/test_student_write.py` 与 `sql/004` 的属主切换语句。
