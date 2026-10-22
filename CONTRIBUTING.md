# 贡献指南

欢迎参与本项目。这份文档说明**怎么提交代码**，以及**哪些改动需要重点审查**。

> 配套细则见 [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md)（分支模型、提交信息、版本标签、回滚）。
> 仓库背景与当前状态见 [README.md](README.md)。

---

## 1. 开始之前

```bash
git clone https://github.com/123asdtte/campus-data-ai.git
cd campus-data-ai
cp .env.example .env     # 用自己的密码，不要复用别人的
```

三条硬性前提：

1. **只用虚构数据**：`samples/` 下的 `SMPL2026xxxx`、`DEMO2021xxxx` 这类样例；
2. **不共用凭据**：数据库密码、Appsmith 加密密钥、HMAC 密钥各自生成，不通过微信/邮件传递；
3. **不碰主库结构**：未经评审不得修改 `sql/` 下的表结构与角色授权。

---

## 2. 分支模型

- `main`：**受保护分支**，只接受通过 PR 合并的提交；
- 功能分支从**最新的 `main`** 切出，不要在别人的分支上继续提交。

命名规范：

| 类型 | 命名 | 示例 |
|---|---|---|
| 功能 | `feature/<简述>` | `feature/student-slice-auth` |
| 修复 | `fix/<简述>` | `fix/import-row-offset` |
| 文档 | `docs/<简述>` | `docs/api-inventory` |
| 杂项 | `chore/<简述>` | `chore/gitignore-keys` |

```bash
git fetch origin && git checkout -b feature/xxx origin/main
```

---

## 3. 提交信息

使用中文或英文均可，格式统一：

```
<类型>: <一句话说明>

<可选正文：为什么这么做、影响范围、需要注意的兼容性>
```

类型：`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf`。

示例：

```
fix(api): 修正表头不在首行时的问题行号偏移

原实现直接用 df.index+2，未考虑表头位于第 N 行，
导致异常指向错误的 Excel 行。改为按表头行数整体平移。
```

---

## 4. 提交 PR 前的检查

```bash
# 1) 前端类型检查与构建（必过）
cd web && npm ci && npm run build

# 2) 容器配置语法检查
docker compose config >/dev/null && docker compose -f docker-compose.web.yml config >/dev/null

# 3) 确认没有夹带敏感文件
git status --short
git diff --cached --stat
```

- 后端测试位于 `import-api/tests`，已接入 CI（关闭态 / 开启态双跑）。如果你新增了业务逻辑，
  请同时补可重复执行的用例，并在 PR 描述里写清**怎么跑、期望看到什么**；安全相关改动必须含负向用例。
- 涉及数据库的改动，必须在**独立数据库**上验证过，并在 PR 中附上验证方式。

---

## 5. PR 描述必须包含

1. **目的**：这次改动解决什么问题；
2. **改动范围**：涉及哪些文件/接口/表；
3. **测试结果**：实际执行的命令与输出摘要（不要只写「已测试」）；
4. **风险与影响**：是否影响存量数据、是否需要迁移、是否改变接口契约；
5. **回退方式**：出问题如何撤回（通常就是 revert 这次提交）。

---

## 6. 必须重点审查的改动

以下类型**至少需要一位其他成员审查**：

- 认证、授权、HMAC 签名、会话与 Cookie；
- 数据范围（学院/部门隔离）、任何 SQL 的 `WHERE` 条件变更；
- 导入流程：解析、字段映射、校验规则、提交与幂等；
- 审计：触发器、`operation_logs` 写入、`actor_user_id` 传递；
- 数据库结构与角色授权（`sql/`、`campus_app` / `campus_ro` 权限）；
- Docker Compose、端口、卷与环境变量；
- 任何引入真实学生数据的可能性。

---

## 7. 禁止事项

- ❌ 直接向 `main` 推送业务代码；
- ❌ 未经批准在正式环境执行数据迁移、批量导入或结构变更；
- ❌ 提交 `.env`、备份文件、上传目录、真实学生数据、令牌；
- ❌ 删除或覆盖既有验收证据：批次 27（2007 行待提交）、批次 37 的暂存文件；
- ❌ 把 RuoYi POC 的实现与文档整理混在同一次提交；
- ❌ 擅自修改仓库权限、邀请成员或变更分支保护规则。

---

## 8. 仓库权限建议（由仓库管理员执行）

- 开发成员授予 **Write** 即可，不需要 Admin；
- `main` 设置分支保护：禁止直接推送、要求至少 1 次审查、要求 CI 通过；
- 若为个人仓库无法配置保护规则，则在团队流程中严格执行「一切经 PR」；
- 成员使用自己的 GitHub 账号，**不要共用个人令牌或本地 `.env`**；
- 成员使用**自己的开发数据库**，与 POC 库、主库都保持分离。

---

## 9. 提交后

- CI 会自动跑前端类型检查与构建；失败请先修再重推；
- 评审意见请逐条回应，不接受「已改」这种无信息量的回复；
- 合并后删除功能分支。

---

## 10. PR 自动评审（AI 评审机器人）

发起 PR 后，流水线会自动执行两类检查：

| 检查 | 触发 | 作用 | 是否阻塞 |
|---|---|---|---|
| **CI**（ci.yml） | push / PR | 前端类型检查与构建、后端语法检查 | 建议修到全绿 |
| **AI 评审**（ai-review.yml） | PR | 把 diff 发给 LLM，评审结论以 PR 评论发布（阻断/建议/确认三级） | **不阻塞**，仅供参考 |

AI 评审的审查重点与项目红线一致：认证绕过、学院数据范围、SQL 参数化、事务与审计一致性、敏感信息、回退方式。

### 评审所需的仓库 Secret（管理员配置一次）

```bash
gh secret set AI_API_KEY  --repo 123asdtte/campus-data-ai   # LLM 平台的 API Key
gh secret set AI_BASE_URL --repo 123asdtte/campus-data-ai   # 如 https://tokenrhythm.studio/v1
gh secret set AI_MODEL    --repo 123asdtte/campus-data-ai   # 如 deepseek-flash
```

未配置时 AI 评审自动跳过（不报错、不阻塞）；配置后**新发起的 PR** 自动获得评审评论。

### 用推理模型时的注意事项（重要）

如果 `AI_MODEL` 是带思考阶段的推理模型（`deepseek-*-flash`、`o*`、`*-thinking` 等），它会先整段输出思维链（`reasoning_content`），再给正文。实测一份 **18KB** 的 diff，300 秒里收到了 **95 万字节**的思维链，始终没进入正文——评审必然失败。

失败说明里会明写这种情况：「模型只产出了思维链，N 秒内没有进入正文」。**这不是网络问题**，改超时也没用。

**脚本默认会自己处理**：正式请求前先发一次极小的探测请求（一段真实 diff 片段 + 64 token 上限），
若发现模型先吐思维链，就依次尝试下面这些已知开关，取第一个能让 `reasoning_content` 归零的，
再发正式请求。整个过程只在日志里留痕（`探测：xxx 生效`），不需要任何配置。

只有探测全部落空（网关不吃已知任何一种开关）时，才需要在仓库 **Variables**（注意不是 Secrets）里手动指定 `AI_EXTRA_BODY`，值为 JSON：

| 网关类型 | 取值 |
|---|---|
| OpenAI o 系列 / 部分兼容层 | `{"reasoning_effort":"none"}` |
| Anthropic 风格 | `{"thinking":{"type":"disabled"}}` |
| vLLM / DeepSeek 原生 | `{"chat_template_kwargs":{"enable_thinking":false}}` |
| 通义 / Qwen 系 | `{"enable_thinking":false}` |

```bash
gh variable set AI_EXTRA_BODY --repo 123asdtte/campus-data-ai --body '{"reasoning_effort":"none"}'
```

配置错了网关会返回 400，评审照样失败但会留痕；不确定就用非推理模型。

其他可调项（同样是 Variables）：`LLM_TIMEOUT`（单次上限，默认 300 秒）、`LLM_RETRY`（额外重试次数，默认 1）、
`PROBE_TIMEOUT`（单次探测上限，默认 30 秒）、`LLM_BUDGET`（探测+请求+重试的总预算，默认 780 秒）。
总预算是为了保证 job 被 kill 之前一定能把失败说明发出去——被 kill 的话，PR 上会一点痕迹都没有。

### 实际发给模型的内容

评审会把 PR diff 发给**外部**模型端点，所以送审范围是收窄过的：

| 规则 | 说明 |
|---|---|
| 路径过滤 | `docs/`、`samples/`、`import-api/wheels/`、`node_modules/`、各类锁文件与二进制（xlsx/csv/png/pdf/whl 等）**不发送**，只在 diff 末尾列出文件名 |
| 体积上限 | 过滤后仍超过 60KB 则截断，并标注「已在此处截断」 |
| 凭据拦截 | diff 命中 AWS AccessKey、私钥头、`sk-`/`ghp_` 形态令牌时**整次评审中止**，只在 PR 上提示命中的类别（不回显内容），不发往外部 |
| 请求方式 | `stream: true` 流式接收，单次上限 300s；超时/5xx 最多重试 1 次（总时长压在 10 分钟内） |

因此**不要**把凭据、真实学生数据写进代码或提交进仓库——即使路径过滤能挡掉一部分，也挡不住你把它写进 `.py`。

### 边界

- AI 评审**不能替代人工审查**：合并决策仍由评审人做出；
- 涉及认证、权限、数据范围、审计的 PR，AI 意见只作为线索，结论以人工核验为准；
- 评审失败（超时/限流/端点不可用/命中凭据拦截）**不阻塞 PR**，但会在 PR 上留一条带 `<!-- ai-review-failed -->` 标记的说明，写清失败原因和日志链接——看到这条说明即代表**本次没有 AI 结论**，不要误当成「评审通过」。同一 PR 上这类说明只会有一条（重跑时原地更新），评审成功后自动删除。
