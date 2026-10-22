# 技术选型决策：复用成熟组件，不迁移若依

> **⚠️ 已被取代（归档）**：本文"不迁移若依"的结论已被后续 POC 与 D1 决策推翻。现行认证架构为 **RuoYi 登录 + Java 网关签名 + FastAPI 二次验证**。
> 现行契约见 [`../INTERNAL-AUTH-SPEC.md`](../INTERNAL-AUTH-SPEC.md)，阶段定义见 [`../../PROJECT-ROADMAP.md`](../../PROJECT-ROADMAP.md)。本文件仅作"为什么改向"的历史档案。

- **状态**：已决策（2026-10-20），待评审后实施
- **范围**：认证、路由授权、审计链路、后台管理
- **前提**：保留 React + TypeScript + FastAPI + PostgreSQL，不重写已跑通的解析与导入闭环
- **核查方式**：GitHub API、PyPI JSON、官方文档（核查日期 2026-10-20）

> **2026-10-20 23:30 补充**：本文第 2 节的若依评估只覆盖了 `RuoYi` 与 `RuoYi-Vue3`（Spring Boot + Vue），**未包含 RuoYi-Vue-Plus 6.X 的官方 React 前端**。
> 该方向的完整核查与迁移方案见 **`docs/RUOYI-PLUS-EVALUATION.md`** 与 **`docs/RUOYI-PLUS-MIGRATION-PLAN.md`**。
> 是否改用 RuoYi-Vue-Plus 由 POC 结果决定；若 POC No-Go，本文第 1 节的 pwdlib + Casbin 选型仍然有效。

---

## 1. 最终选型

| 层次 | 组件 | 版本 | 许可证 | 职责边界 |
|---|---|---|---|---|
| 密码哈希 | `pwdlib[argon2]` | 0.3.1 | MIT | 只做哈希与校验 |
| 会话 | **自建**（`auth_session` 表 + HttpOnly Cookie） | — | — | 签发、校验、过期、撤销 |
| 路由授权 | `casbin`（PyCasbin） | 1.43.0 | Apache-2.0 | 只判定「角色能否对某资源做某动作」 |
| 数据范围 | **自建**查询约束 | — | — | 学院级过滤，Casbin 不负责 |
| 数据库权限 | 现有 `campus_ro` / `campus_app` | — | — | 连接级兜底 |
| 后台管理页面 | **自建**（React） | — | — | Casbin 不生成 UI |

**一句话**：密码交给 pwdlib，判定交给 Casbin，会话、数据范围、管理界面自己写。

---

## 2. 若依（RuoYi）评估

### 2.1 官方仓库核实

| 仓库 | 技术栈 | 许可证 | 星标 | 最近推送 |
|---|---|---|---:|---|
| `yangzongzhuan/RuoYi` | Spring Boot + Shiro + Thymeleaf | MIT | 8,613 | 2026-10-10 |
| `yangzongzhuan/RuoYi-Vue3` | Spring Boot + Spring Security + JWT + Vue3/Vite/Element Plus | MIT | 6,787 | 2026-09-16 |

两者均**活跃、MIT 许可、可用于商业项目**，能力本身没有问题。

### 2.2 它有什么

用户管理、角色管理、菜单权限、部门管理、数据范围（全部/自定义/本部门/本部门及以下/仅本人）、操作日志、代码生成器。

### 2.3 三种接入方式的真实成本

| 方式 | 要做的事 | 成本 | 结论 |
|---|---|---|---|
| **整体迁移** | React → Vue 重写；FastAPI → Spring Boot 重写导入、解析、校验；重建 12 个接口与审计触发器；重跑 20 项浏览器验收 | 数周，且现有导入闭环全部推倒 | **否决** |
| **混合部署** | 额外跑一套 Java 服务；两套用户体系；会话无法共享；导入仍走 FastAPI，权限判定在 Java 侧，身份要跨进程传递 | 中高，且引入第二技术栈的长期维护成本 | 否决 |
| **借鉴设计** | 参考它的「角色—菜单—数据范围」分层，用 Python 组件实现 | 低 | **采纳** |

**决策：不迁移，只借鉴。** 理由不是若依不好，而是为了权限功能去重写一个已经通过验收的业务闭环，投入产出不成立。

> 该结论仅针对 Spring Boot + Vue 的 RuoYi / RuoYi-Vue3。RuoYi-Vue-Plus 6.X 另有官方 React 前端，已单独立项评估，结论待 POC（见 `RUOYI-PLUS-EVALUATION.md`）。

---

## 3. 认证组件评估：pwdlib

### 3.1 核查结果

| 项 | 值 |
|---|---|
| 版本 | 0.3.1 |
| 许可证 | MIT |
| Python 要求 | ≥ 3.10（本项目容器为 3.12，满足） |
| 维护状态 | 仓库 `frankie567/pwdlib`，181 星，最近推送 2026-08-17，开放 issue 1 条 |
| 官方推荐 | FastAPI 文档原文：*"pwdlib is a great Python package to handle password hashes."*、*"The recommended algorithm is 'Argon2'."* |
| 安装 | `pwdlib[argon2]` |
| 用法 | `PasswordHash.recommended()` → `.hash(pwd)` / `.verify(pwd, hash)` |

### 3.2 它能覆盖什么、不能覆盖什么

| 能力 | 是否由 pwdlib 提供 |
|---|---|
| Argon2id 哈希与校验 | ✅ |
| 防时序攻击（不存在的用户也走一次校验） | ✅（需自行使用 DUMMY_HASH） |
| 会话签发 / 过期 / 撤销 | ❌ **自建** |
| 登录失败限流 | ❌ **自建** |
| 用户表、角色表 | ❌ **自建** |
| 初始管理员创建 | ❌ **自建（受控命令）** |

> 这一点必须写清楚：pwdlib 只解决「密码怎么存」，不解决「谁登录了、能待多久、怎么踢下线」。

### 3.3 未选方案

| 方案 | 为什么不用 |
|---|---|
| `passlib` | FastAPI 官方已转向 pwdlib；passlib 对新版 bcrypt 有兼容告警 |
| `fastapi-users` | 自带用户模型与路由，但与现有 `campus` schema、审计触发器、导入业务耦合成本高，且默认 JWT |
| JWT 存 localStorage | XSS 可读、无法服务端撤销、登出只是删本地 |
| Keycloak / Auth0 | 新增一套身份服务与运维负担，当前 4 个角色用不上 |

---

## 4. 权限组件评估：PyCasbin

### 4.1 核查结果

| 项 | 值 |
|---|---|
| 版本 | 1.43.0 |
| 许可证 | Apache-2.0 |
| Python 要求 | ≥ 3.3 |
| 维护状态 | `apache/casbin-pycasbin`，1,776 星，**最近推送 2026-10-20（当天）**，开放 issue 2 条 |
| 模型 | ACL / RBAC / ABAC / 域内 RBAC（`dom`） |

### 4.2 一处需要纠正的认知

> 原判断：「Casbin 官方提供 FastAPI 集成教程」。

**核查结果：不准确。** Casbin 官方「Middleware」文档只列了 Go 生态（Gin、Echo、Fiber、Traefik、Caddy 等），**没有 Python/FastAPI 中间件**。

Python 侧的正确做法是自己写一个 FastAPI 依赖项，调用 `enforcer.enforce(sub, obj, act)`，大约 20 行：

```python
def require(obj: str, act: str):
    def dep(user = Depends(current_user)):
        if not enforcer.enforce(user.role, obj, act):
            raise HTTPException(403, "无权限")
        return user
    return dep
```

这不影响选型结论，但**不能按「官方中间件」预估工作量**。

### 4.3 策略存储

| 方案 | 依赖变化 | 评价 |
|---|---|---|
| 默认 FileAdapter（CSV） | 无 | 策略无法在线编辑，不适合多用户 |
| `casbin-sqlalchemy-adapter` 1.4.0（Apache-2.0） | **新增 SQLAlchemy**（本项目目前只用 psycopg） | 为一个适配器引入整套 ORM，不划算 |
| **自写只读适配器**（推荐） | 无 | Adapter 接口很小，约 40 行：从 `auth_policy` 表读 `p_type,v0,v1,v2` 装入模型 |
| 启动时全量载入内存 + 变更后 `load_policy()` | 无 | 4 个角色、约 20 条策略，内存驻留完全够 |

### 4.4 边界（必须写进设计）

- Casbin **不生成**任何用户/角色管理页面；
- Casbin **不做**数据范围过滤（学院级隔离要在 SQL 层拼条件）；
- Casbin **不替代**数据库权限（即使应用判定通过，`campus_ro` 仍写不进去）；
- Casbin **不记录**审计，审计仍由触发器完成。

---

## 5. 四层安全模型（防止把某一层当成全部）

| 层 | 解决什么 | 由谁实现 | 当前状态 |
|---|---|---|---|
| L1 认证 | 你是谁 | pwdlib + 会话 + Cookie | 未实现 |
| L2 路由授权 | 你这个角色能不能调这个接口 | Casbin + FastAPI 依赖 | 未实现 |
| L3 数据范围 | 你能看到哪些记录 | SQL 条件（学院/本人） | 未实现，规则待业务确认 |
| L4 数据库权限 | 就算前面都被绕过，能写多深 | PostgreSQL 角色 | **已部分具备**（`campus_ro` 只读已验证） |

**只有四层同时成立才算「有权限体系」**。L4 已经可用，L1–L3 待建。

---

## 6. 许可证与维护状态汇总

| 组件 | 许可证 | 商用 | 维护 | 风险 |
|---|---|---|---|---|
| RuoYi / RuoYi-Vue3 | MIT | 允许 | 活跃 | 不用，仅参考 |
| pwdlib | MIT | 允许 | 近两月有提交 | 低 |
| PyCasbin | Apache-2.0 | 允许 | 当天有提交 | 低 |
| casbin-sqlalchemy-adapter | Apache-2.0 | 允许 | 版本 1.4.0 | 不采用（引入 SQLAlchemy） |

许可证均兼容本项目（内部系统，无再分发限制）。

---

## 7. 决策影响

**变简单的部分**：不用维护 Java 服务；不用自研密码学；权限策略可热更新；角色调整不改代码。

**变复杂的部分**：会话表、登录限流、CSRF、用户管理页面仍需自建；Casbin 的 FastAPI 集成要自己写依赖；数据范围不能指望 Casbin。

**不变的部分**：导入闭环（解析 → 映射 → 校验 → 提交 → 审计）完全不动，认证只是加在它前面的一层门。
