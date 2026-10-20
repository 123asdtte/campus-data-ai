# React 前端迁移：检查结果与实施计划

**日期：** 2026-10-20　**范围：** 本轮只做骨架 + 学生查询 + 数据导入两页
**原则：** 不改表结构、不动现有数据、不破坏 Appsmith / PostgreSQL / Import API

---

## 一、检查结果（只读核查）

### 1.1 运行状态

| 容器 | 镜像 | 状态 | 端口 |
|---|---|---|---|
| campus-appsmith | appsmith-ce:v2.5.0 | healthy | 127.0.0.1:8081 |
| campus-db | postgres:16.15-alpine | healthy | 127.0.0.1:55432 |
| campus-import-api | campus-import-api:0.1.0 | healthy | 127.0.0.1:8010 |

数据量：students 221、student_changes 305、import_batches 11、import_issues 33、operation_logs 530。均为虚构数据。

### 1.2 数据库结构

5 张表 + 2 个视图，全部在 `campus` schema：

| 表 | 主键 | 关键约束 |
|---|---|---|
| `students` | id | `student_no` 唯一非空；CHECK 限制状态枚举与年份范围 |
| `student_changes` | id | 外键 → students；CHECK 限制异动类型/记录状态 |
| `import_batches` | id | `batch_code` 唯一；`file_sha256` 用于重复文件识别；状态机 uploaded→validated→imported/failed |
| `import_issues` | id | 外键 → import_batches；8 类 issue_code |
| `operation_logs` | id | 审计表，应用侧只读；触发器写入 |
| `v_student_changes` | 视图 | 异动 + 学生姓名/学院/班级 |
| `v_import_batch_summary` | 视图 | 批次 + 异常计数 |

### 1.3 现有 API 实际路由

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/imports/preview` | multipart 上传预览 |
| POST | `/imports/preview-base64` | base64 上传预览 |
| POST | `/imports/{id}/validate` | 校验 |
| POST | `/imports/{id}/commit` | 提交（幂等） |
| GET | `/imports/{id}` | 批次详情 + 异常 |
| GET | `/imports` | 批次列表 |

统一错误返回 `{"detail": "..."}`；状态码 400/404/409/413/422/500/503。

### 1.4 接口缺口（关键结论）

**学生查询、学生详情、学籍异动查询接口全部不存在。** 现有 API 只覆盖导入流程。

因此 React 前端无法直接完成「学生信息查询」页。按任务要求，浏览器不得直连 PostgreSQL，需在 FastAPI 中补充**只读**查询接口。

### 1.5 身份、权限与审计现状

| 项 | 现状 | 对本轮的影响 |
|---|---|---|
| 登录/认证 | **不存在** | 前端不伪造登录，顶部显示「本地测试环境」，操作人取自可配置标识 |
| `X-Actor` | 客户端自报，可伪造 | 仅在页面上显示为「当前操作人（未认证）」 |
| 角色权限 | 仅数据库层（campus_app / campus_ro），应用层无 | 前端不做按钮级权限伪装 |
| 审计 | 触发器写入，Import API 可注入 actor_user_id | 前端调用时透传 X-Actor，不承诺可信 |

这三项在交付说明中必须标为「待实现 / 存在安全风险」，不得写成已完成。

### 1.6 部署与备份

- `docker-compose.yml` 定义三服务，端口均绑定 127.0.0.1。
- 备份脚本 `scripts/backup.sh` 正常，已有一次恢复演练记录。
- Docker 数据目录 `F:\DockerData\docker`，F 盘余量 26 GB。

---

## 二、接口补充方案（最小改动）

不改表结构、不改现有路由，仅在 `import-api` 中新增三个只读接口。

| 方法 | 路径 | 参数 | 返回 |
|---|---|---|---|
| GET | `/students` | `keyword`、`college`、`class_name`、`status`、`include_inactive`、`page`、`page_size` | `{items[], total, page, page_size}` |
| GET | `/students/{student_no}` | — | 学生对象 + 最近 20 条异动 |
| GET | `/meta/filters` | — | 学院列表、班级列表、状态计数 |

约束：
- 全部使用参数化查询（psycopg），不拼接 SQL。
- 复用 `campus_app` 连接池（已有 SELECT 权限），不新建账号、不改授权。
- 单个接口返回行数上限 200，默认 20。
- 新增代码放在 `import-api/app/queries.py`，`main.py` 只增加路由声明。

若后续要分权，可让读接口改用 `campus_ro`；本轮不做，避免引入第二个连接池。

---

## 三、前端技术方案

### 3.1 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 构建 | Vite 7 + React 19 + TypeScript | 启动快，类型检查独立 |
| UI | Ant Design 5 | 表格/表单/上传组件齐全，中文生态成熟 |
| 路由 | react-router-dom 7 | 两页 + 布局足够 |
| 请求 | 自封装 fetch + AbortController | 不引入 axios，超时与取消可控 |
| 状态 | React 局部状态 + 自定义 hook | 两页规模不需要 Redux |

### 3.2 目录结构

```text
web/
├─ index.html
├─ package.json
├─ vite.config.ts          # /api 代理到 127.0.0.1:8010
├─ tsconfig*.json
├─ .env.example            # VITE_API_BASE
└─ src/
   ├─ main.tsx             # AntD ConfigProvider zh_CN
   ├─ App.tsx              # 路由
   ├─ styles.css
   ├─ api/
   │  ├─ client.ts         # 超时、错误归一化、X-Actor
   │  ├─ types.ts          # 与后端字段一一对应
   │  ├─ students.ts
   │  └─ imports.ts
   ├─ components/
   │  ├─ AppLayout.tsx     # 侧边栏 + 顶部 + 面包屑
   │  └─ ErrorState.tsx    # 统一错误态
   └─ pages/
      ├─ StudentsPage.tsx
      └─ ImportPage.tsx
```

### 3.3 请求封装约定

- 基址：`import.meta.env.VITE_API_BASE || '/api'`，开发期由 Vite 代理到 `http://127.0.0.1:8010`。
- 超时：普通查询 15 s，导入提交 60 s（后端最长处理 1 万行）。
- 错误归一化：`{ status, code, message, detail }`，页面只消费 `message`。
- 操作人：`VITE_ACTOR` 或本地存储的展示名，随 `X-Actor` 发送，界面明确标注「未认证」。

### 3.4 页面一：学生信息查询

- 顶部：关键词搜索（学号/姓名）、学院下拉、班级下拉、状态下拉、显示停用开关、重置。
- 表格：服务端分页（20/50/100），列含学号、姓名、学院、专业、班级、入学年份、状态、更新时间；横向滚动 `scroll={{ x: 1200 }}`。
- 详情：右侧 Drawer，展示基本信息 + 最近异动列表。
- 状态：加载骨架、空数据（Empty）、错误（Result + 重试）。
- 所有数据来自 `/students`，无 mock。

### 3.5 页面二：学生数据导入

流程固定为四步，用 Steps 组件呈现：

1. 选择文件（限制 .xlsx/.csv，≤10 MB）+ 选择目标类型
2. 预览：调用 `preview-base64`，展示列映射、前 20 行、缺失列
3. 校验：调用 `validate`，展示有效/异常数量与异常明细表（行号、字段、代码、说明）
4. 提交：仅在 `status=validated && valid_rows>0` 时启用；二次确认弹窗显示「有效 N 行 / 异常 M 行」

保护措施：
- 提交按钮在请求期间 disabled，防重复点击。
- 后端已用状态机保证幂等，前端捕获 409 并提示「该批次已提交」。
- 超时/中断后可用「按批次号恢复」输入框调用 `GET /imports/{id}` 还原状态。
- 失败展示 `detail` 原文，不做笼统「操作失败」。

### 3.6 明确不做

- 不做登录页与假权限（只在顶部标注环境与未认证身份）。
- 不做 Dify / AI 助手入口。
- 不建空壳页面；侧边栏只放本轮真实存在的两项，其余置灰并标注「未实现」。
- 不改 `docker-compose.yml`；前端先以 `npm run dev` 运行，容器化方案在文档中给出、待确认后启用。

---

## 四、实施顺序与验收

| 步骤 | 内容 | 验收 |
|---|---|---|
| 1 | 补充 3 个只读接口 | `curl` 返回分页数据，SQL 注入字符不生效 |
| 2 | 前端骨架 + 布局 | `npm run build` 通过，`npm run dev` 可访问 |
| 3 | 学生查询页 | 搜索/筛选/分页/详情均有真实数据 |
| 4 | 导入页 | 预览→校验→提交全链路，异常行号正确 |
| 5 | 回归 | 重复提交 409、错误文件提示、Appsmith 仍可用 |
| 6 | 文档 | README 增加前端启动与排查 |

测试结果按「已通过 / 未通过 / 未执行 / 存在安全风险」四类分别列出，不合并表述。
