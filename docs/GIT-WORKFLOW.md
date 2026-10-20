# Git 工作流

本仓库为校内数据平台的本地验证工程。以下约定用于保持历史可读、可回滚。

---

## 1. 绝对不入库的内容

| 内容 | 原因 | 保护方式 |
|---|---|---|
| `.env` / 任何真实凭据 | 含数据库密码与 Appsmith 密钥 | `.gitignore`，仓库只保留 `.env.example` |
| `backups/*.sql.gz` | 数据库快照可能含个人信息 | `.gitignore` |
| `campus_uploads` 卷中的原始导入文件 | 可能是真实学生名单 | 卷不在仓库内 |
| `web/node_modules`、`web/dist` | 可重建产物 | `.gitignore` |
| `import-api/wheels/*.whl` | 约 45 MB，且可按脚本重建 | `.gitignore` + `scripts/fetch-wheels.sh` |

提交前自检：

```bash
git status --short
git diff --cached --name-only | grep -E '\.env$|\.sql\.gz$|node_modules' && echo "拦截：发现敏感文件"
```

---

## 2. 分支模型

| 分支 | 用途 | 规则 |
|---|---|---|
| `main` | 可运行状态 | 不直接提交破坏性改动；每次合并前跑 `npm run build` 与 `docker compose ps` |
| `feat/<主题>` | 新功能 | 从 `main` 切出，完成后合回 |
| `fix/<主题>` | 缺陷修复 | 同上 |
| `chore/<主题>` | 依赖、配置、文档 | 可小步提交 |

当前为单人开发，允许直接在 `main` 上小步提交；多人协作时必须走分支 + PR。

---

## 3. 提交信息

格式：`<type>(<scope>): <中文简述>`

| type | 含义 |
|---|---|
| `feat` | 新增能力 |
| `fix` | 修复缺陷 |
| `docs` | 文档 |
| `refactor` | 不改行为的重构 |
| `chore` | 构建、依赖、配置 |
| `test` | 测试 |

scope 取值：`db`、`api`、`web`、`deploy`、`docs`、`repo`。

示例：

```text
feat(api): 新增学生查询与统计总览接口
fix(db): 审计触发器改用 session_user 记录真实角色
docs: 补充导入接口契约与安全清单
```

一次提交只做一件事。数据库结构变更必须与对应 SQL 文件同提交。

---

## 4. 版本标签

采用语义化版本，标签只在可运行状态打：

```bash
git tag -a v0.1.0 -m "阶段 1：数据库 + 导入服务 + Appsmith"
git tag -a v0.2.0 -m "阶段 2：React 管理界面（总览/查询/导入）"
git push origin --tags
```

---

## 5. 回滚

```bash
git log --oneline            # 找到目标提交
git revert <commit>          # 生成反向提交，保留历史
```

不使用 `git reset --hard` 处理已推送的历史；不使用 `push --force` 覆盖 `main`。

数据库回滚与代码回滚分开处理：代码用 `revert`，数据用 `scripts/restore.sh`。
