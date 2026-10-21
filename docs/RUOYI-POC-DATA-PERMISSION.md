# RuoYi POC 数据权限专项验证

- **日期**：2026-10-21 09:54–10:20
- **环境**：`ruoyi-poc` 隔离栈（PG 16.15 @55433、Redis @6381、FastAPI 内网、Java @9180）
- **后端版本**：`dromara/RuoYi-Vue-Plus` v6.0.0，commit `7180b52`
- **结论**：**两类数据权限均通过**，但必须分开陈述——见 §2

---

## 1. 为什么要分成两类测试

实际调用链是：

```
浏览器 → Java(9180) → FastAPI(内网) → PostgreSQL
```

学生查询与修改由 **FastAPI 用 psycopg 直接执行 SQL**，不经过 Java 的 MyBatis-Plus。因此：

- 框架的 `@DataPermission` 只会改写**经过 Java Mapper 的 SQL**；
- 即使 Mapper 侧测试全绿，**也不能**据此推断 FastAPI 发出的 SQL 存在学院隔离。

所以本报告分两节：§3 框架能力，§4 实际业务路径。**§4 才是决定混合架构是否安全的那一节。**

---

## 2. 结论摘要

| 类别 | 结论 | 依据 |
|---|---|---|
| **A. 框架 Mapper 数据权限** | **通过** | `data_scope=3` 的用户只能看到本部门用户；超管可见全部 |
| **B. 实际业务路径数据权限** | **通过** | 经 Java 代理的 8 项矩阵全部符合预期，跨学院读写被拒且数据库无变更 |
| C. 哪些业务 SQL 不经过 Java Mapper | **全部学生业务 SQL** | 解析、映射、校验、写入均在 `import-api`（Python/psycopg）内完成 |
| D. 若学生 CRUD 迁到 Java | 可复用框架能力，但需映射 | 需把 `college_name` 映射到 `sys_dept`，并保证查询 SQL 别名满足数据权限解析要求 |

---

## 3. A. 框架 Mapper 数据权限

### 3.1 实现依据（读 commit 7180b52 的代码，不靠注解名推断）

| 项 | 位置 | 结论 |
|---|---|---|
| 注解 | `org.dromara.common.mybatis.annotation.DataPermission` | 打在 Service/Mapper 方法上 |
| 拦截 | `DataPermissionInterceptor`（MyBatis-Plus 拦截器链） | 在 SQL 执行前改写 WHERE 条件 |
| 数据来源 | 当前登录用户的 `deptId` + 角色的 `sys_role.data_scope` | 部门树 `sys_dept` + `sys_role_dept` |
| 范围取值 | 1=全部、2=自定义、3=本部门、4=本部门及以下、5=仅本人 | 见 `sys_role.data_scope` |
| 列名要求 | 注解上的 `deptAlias` / `userAlias` 必须与 SQL 里的别名一致 | 否则无法定位并追加条件 |

### 3.2 测试数据

| 部门 | dept_id | 用户 | 角色 | data_scope |
|---|---|---|---|---|
| 计算机学院 | 1762000000000000101 | `poc_college_a` | `poc_college` | **3（本部门）** |
| 电子信息学院 | 1762000000000000102 | `poc_college_b` | `poc_college` | 3 |

### 3.3 实测（`GET /system/user/list`，该查询带 `@DataPermission(deptAlias="d", userAlias="u")`）

| 登录用户 | 可见用户数 | 可见账号 |
|---|---:|---|
| `poc_college_a`（计算机学院） | **1** | `poc_college_a` |
| `poc_college_b`（电子信息学院） | **1** | `poc_college_b` |
| `admin`（超管，范围=全部） | **6** | admin, test, test1, poc_readonly, poc_college_a, poc_college_b |

**结论：框架数据权限在真实 SQL 上生效，跨部门不可见。**

---

## 4. B. 实际业务路径数据权限（决定性）

### 4.1 测试数据

| 学生 | 学院 |
|---|---|
| POCA0001 / POCA0002 | 计算机学院 |
| POCB0001 / POCB0002 | 电子信息学院 |

学院归属由**登录用户所属部门**决定：Java 代理把 `LoginHelper.getLoginUser().getDeptName()` 作为签名声明的一部分传给 FastAPI，FastAPI 据此强制过滤。

### 4.2 实测矩阵（全部经 Java 代理入口 `9180/poc/proxy/*`）

| # | 用例 | 期望 | 实测 |
|---|---|---|---|
| A1 | 学院A用户列学生 | 只含本学院 | **通过**：`total=5, scope=计算机学院`，全部为计算机学院记录 |
| A2 | 学院A用户查学院B学生 POCB0001 | 拒绝 | **通过**：403 `越权：不能查看其他学院的学生` |
| A3 | 学院A用户改学院B学生 POCB0001 | 拒绝且不落库 | **通过**：403 `越权：不能修改其他学院的学生`；DB 复查 `POCB0001 | 乙同学 | 电子信息学院` **未变** |
| A4 | 学院A用户搜索学院B学号 | 查不到 | **通过**：`total=0`（过滤发生在 SQL 层，不是展示层） |
| A5 | 学院A用户查本学院 POCA0001 | 允许 | **通过**：200，返回本人学院记录 |
| A6 | 学院B用户列学生 | 只含本学院 | **通过**：`total=3, scope=电子信息学院` |
| A7 | 低权限用户（无角色）调代理列表 | 拒绝 | **通过**：`code=403`（Java 侧 `@SaCheckPermission` 拦截） |
| A8 | 学院A用户改本学院学生 | 允许且留审计 | **通过**：200，审计 `actor_user_id=ry:poc_college_a`、`actor_db_role=campus_app`、`action=update`、`changed_fields={student_name, updated_at}` |

> A8 首次执行时把值改成相同值，触发器按设计不记「无变化」的 UPDATE，因此取到的是此前的 insert 记录；改为真实变更后复测通过。

### 4.3 结论

**当前混合架构下，学院级数据范围在服务端被可靠执行**：查询、详情、搜索、修改四个入口全部拦截，越权请求不产生任何数据库变更，合法操作留下可信审计。

---

## 5. C. 哪些业务 SQL 不经过 Java Mapper

| 业务 | 执行位置 | 是否受框架数据权限约束 |
|---|---|---|
| Excel 解析 / 表头识别 / 字段映射 | `import-api`（Python） | 否 |
| 数据校验（重复学号、枚举、日期） | `import-api` | 否 |
| 导入落库（students / student_changes） | `import-api` + PG 触发器 | 否（靠 `campus.actor_user_id` 事务变量） |
| 学生列表 / 详情 / 修改（本次新增的 POC 接口） | `import-api`（Python/psycopg） | **否** —— 由 Python 侧按签名声明的学院强制过滤 |
| 系统管理类查询（用户、角色、菜单、字典） | Java Mapper | **是** |

**结论：框架数据权限只覆盖系统管理类 SQL；学生业务 SQL 的隔离责任在 Python 侧。** 这一条必须在迁移评估中保留，不能因为「若依有数据权限」就认为学生数据也自动隔离。

---

## 6. D. 若未来把学生 CRUD 迁到 Java

| 事项 | 结论 |
|---|---|
| 能否不改框架核心授权代码 | **可以**：`@DataPermission` 只需在 Service 方法上标注，并让 SQL 别名与 `deptAlias`/`userAlias` 对齐 |
| 映射方式 | ① 每个学院建一条 `sys_dept`；② `students.college_name` ←→ `sys_dept.dept_name`；③ 建议后续加 `dept_id` 列做稳定关联（当前是名称字符串，部门改名会断） |
| 需要改造的查询 | 所有学生相关 Mapper 的 SQL 都要带 `d`（部门表别名）才能被数据权限改写；`v_*` 视图同样适用 |
| 风险 | 名称映射脆弱；建议迁移时顺带把 `college_name` 升级为外键/编码列 |

---

## 7. 复现方式

```bash
cd Z:/ai/本地部署/ruoyi-plus-poc
bash test_datascope.sh          # A1–A8 全矩阵
docker exec ruoyi-poc-db psql -U ruoyi -d ruoyi \
  -c "SELECT actor_user_id, actor_db_role, action, count(*) FROM campus.operation_logs GROUP BY 1,2,3;"
```

夹具脚本：`sql/03_datascope_fixture.sql`（部门/用户/角色/学生）、`sql/04_proxy_perms.sql`（代理接口权限点）。

---

## 8. 本轮未完成

- **React 前端（`plus-ui-react`）验收**：见 `RUOYI-POC-AUTH-RESULTS.md` 补记章节。
- 框架级数据权限**未**在学生表上验证（学生表不归 Java Mapper 管），只验证了 `sys_user` 查询这条真实链路。
- `--api-decrypt.enabled=false` 仍为 POC 专用配置。
