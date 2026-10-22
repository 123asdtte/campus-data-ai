# Import API 接口契约

**版本：** 0.1.0　**服务：** `campus-import-api`　**地址：** `http://127.0.0.1:8010`

职责边界：只做「解析 → 列映射 → 校验 → 事务提交」。不做权限判定、不做审批、不调用 AI。

---

## 1. 调用顺序

```text
preview（上传 + 解析 + 预览）
   → validate（结构校验 + 业务校验，写入 import_issues）
   → commit（事务写入有效行，幂等）
   → get（查询状态与报告）
```

`validate` 与 `commit` 都必须先有 `preview` 产出的 `batch_id`。

---

## 2. 通用约定

| 项 | 说明 |
|---|---|
| 身份 | 关闭态（默认）：请求头 `X-Actor`，写入 `operation_logs.actor_user_id`，仅用于演示审计链路、**可伪造**；开启态：`X-Internal-*` 签名声明，`actor_user_id` 来自验签用户。详见 §9 |
| 编码 | 请求与响应均为 UTF-8；响应为 JSON |
| 限制 | 单文件 ≤ 10 MB、≤ 10,000 行（`.env` 可调）；允许 `.xlsx` / `.xlsm` / `.csv` |
| 暂存 | 上传文件暂存于卷 `campus_uploads`，提交成功后删除（`KEEP_UPLOAD_FILES=false`） |
| 行号 | 所有 `row_number` 为 **Excel 实际行号**（表头为第 1 行，数据从第 2 行开始） |

---

## 3. 接口明细

### 3.1 `POST /imports/preview`

`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | xlsx / csv |
| `target_type` | text | 是 | `students` 或 `student_changes` |

**响应 200**

```json
{
  "batch_id": 7,
  "batch_code": "IMP-20261020-155353-70762C",
  "target_type": "students",
  "status": "uploaded",
  "total_rows": 10,
  "missing_required": [],
  "column_mapping": {"学号": "student_no", "姓名": "student_name"},
  "unmapped_columns": ["备注"],
  "field_labels": {"student_no": "学号", "student_name": "姓名"},
  "preview": [{"__row": 2, "student_no": "SMPL20260011", "student_name": "测试学生11"}],
  "issues": []
}
```

- `status` 为 `failed` 时，`issues` 内含一条 `COLUMN_MAPPING_REQUIRED`，`missing_required` 列出缺失字段。
- `issues` 中若出现 `DUPLICATE_BATCH`（severity=`warning`），表示同一 `file_sha256` 此前已成功导入，需人工确认是否重复导入。
- `preview` 最多 20 行，保留原始值（未做枚举转换）。

### 3.2 `POST /imports/preview-base64`

供 Appsmith `FilePicker` 使用（该组件只能提供 base64）。

```json
{
  "filename": "students_demo.xlsx",
  "content_base64": "UEsDBBQ...",
  "target_type": "students"
}
```

响应结构同 3.1。

### 3.3 `POST /imports/{batch_id}/validate`

无请求体。重新解析暂存文件，执行全部校验，清空并重写该批次的 `import_issues`。

**响应 200**

```json
{
  "batch_id": 2,
  "status": "validated",
  "total_rows": 15,
  "valid_rows": 10,
  "invalid_rows": 5,
  "error_count": 5,
  "warning_count": 0,
  "column_mapping": {"学号": "student_no"},
  "issues": [
    {"row_number": 12, "field_name": "student_name", "issue_code": "MISSING_REQUIRED",
     "severity": "error", "issue_message": "该字段为必填项"}
  ]
}
```

- 已 `imported` 的批次再次校验返回 **409**。
- `validated` 状态可重复校验（结果覆盖上一次），用于用户修正后重新上传前的对比。

### 3.4 `POST /imports/{batch_id}/commit`

无请求体。在单个事务内：状态推进 → 重新校验 → 写入有效行 → 更新计数。

**响应 200**

```json
{
  "batch_id": 2,
  "batch_code": "IMP-20261020-154952-CB73A4",
  "status": "imported",
  "inserted_rows": 10,
  "skipped_rows": [],
  "invalid_rows_excluded": 5
}
```

**幂等语义**：状态更新使用 `WHERE batch_status = 'validated'` 条件，重复提交命中 0 行即返回 **409**，不会重复写入。

**并发保护**：
- 学生导入依赖唯一约束 `students_student_no_key`，冲突时 `ON CONFLICT DO NOTHING` 并记为 `warning`。
- 异动导入通过 `INSERT ... SELECT ... WHERE student_no = ?` 关联，学生不存在则不写入。

### 3.5 `GET /imports/{batch_id}`

返回批次元数据与异常明细（最多 500 条）。用于刷新页面或中断后恢复查看。

### 3.6 `GET /imports?limit=50`

批次列表，按创建时间倒序，`limit` 上限 200。

### 3.7 `GET /health`

```json
{"status": "ok"}
```

`/health` 为 liveness，只返回 `{"status":"ok"}`；数据库就绪由 `/health/ready` 检查，不可用时返回 **503**，不谎报健康。

---

## 4. 异常代码

| 代码 | 级别 | 触发条件 | 责任层 |
|---|---|---|---|
| `MISSING_REQUIRED` | error | 必填字段为空 | Pandera / 预处理 |
| `VALUE_TOO_LONG` | error | 字段长度超限（姓名 > 100、原因 > 500 等） | Pandera |
| `INVALID_ENUM` | error | 枚举值、数值类型或范围不合规 | Pandera / 预处理 |
| `INVALID_DATE` | error | 日期无法解析 | 预处理 |
| `DUPLICATE_STUDENT_NO` | error / warning | 学号在文件内重复、已存在于数据库、或提交时冲突 | Pandera / 业务校验 / 数据库约束 |
| `UNKNOWN_STUDENT` | error | 异动记录引用的学号在数据库中不存在 | 业务校验 |
| `DUPLICATE_BATCH` | warning | 文件哈希此前已成功导入 | 批次校验 |
| `COLUMN_MAPPING_REQUIRED` | error | 缺少必需列，批次直接置 `failed` | 列映射 |

说明：`student_changes` 允许同一学生在同一文件中出现多条异动记录，因此**不做**文件内学号唯一性检查。

---

## 5. HTTP 状态码

| 码 | 含义 |
|---|---|
| 200 | 业务性结果（含校验失败，需读 `status` / `issues`） |
| 400 | 参数错误、不支持的文件类型、空文件、base64 解码失败 |
| 404 | 批次不存在 |
| 409 | 状态冲突（已导入仍校验、重复提交、暂存文件缺失） |
| 413 | 超出大小或行数上限 |
| 422 | 缺列导致无法校验 |
| 503 | 数据库不可用 |

---

## 6. 列名映射

| 学生信息 | 学籍异动 |
|---|---|
| 学号 / 学生学号 → `student_no` | 学号 / 学生学号 → `student_no` |
| 姓名 / 学生姓名 → `student_name` | 异动类型 / 学籍异动类型 → `change_type` |
| 学院 / 院系 / 二级学院 → `college_name` | 生效日期 / 异动日期 / 发生日期 → `effective_date` |
| 专业 → `major_name` | 异动原因 / 原因 → `change_reason` |
| 班级 / 行政班 → `class_name` | 记录状态 → `record_status` |
| 入学年份 / 年级 → `enrollment_year` | |
| 在校状态 / 学籍状态 → `student_status` | |

未识别的列会被忽略并列入 `unmapped_columns`，不阻止导入。

---

## 7. 枚举转换

| 字段 | 接受的中文值 | 内部代码 |
|---|---|---|
| `student_status` | 在校 / 休学 / 退学 / 毕业 / 其他 | enrolled / suspended / withdrawn / graduated / other |
| `change_type` | 休学 / 复学 / 退学 / 转专业 / 转学 / 保留学籍 / 其他 | suspend / resume / withdraw / transfer_major / transfer_school / retain / other |
| `record_status` | 草稿 / 待复核 / 已确认 / 已退回 | draft / pending_review / confirmed / returned |

未命中的值不会被静默纠正，而是产生 `INVALID_ENUM`。

---

## 8. 自动识别与字段映射（v0.3）

### 8.1 变更点

上传后不再要求表头与固定列名完全一致。服务端会：

1. 遍历工作簿的所有工作表，在前 15 行内寻找表头行；
2. 用别名表把列名映射到业务字段，给出匹配方式与置信度；
3. 无法识别、存在歧义或冲突时如实标注，不静默猜测。

### 8.2 新增请求参数（均为可选，向后兼容）

| 位置 | 参数 | 说明 |
|---|---|---|
| `POST /imports/preview`（form） | `sheet_name` | 指定工作表 |
| | `header_row` | 指定表头行号（1 起） |
| | `mapping` | JSON 字符串：`{"原始列名":"字段名"}`，值可为 `null` 表示不导入该列 |
| `POST /imports/preview-base64`（JSON） | `sheet_name` / `header_row` / `mapping` | 同上，类型为字符串/整数/对象 |

### 8.3 新增响应字段

| 字段 | 说明 |
|---|---|
| `sheet_name` / `header_row` | 实际使用的工作表与表头行 |
| `sheets` | 所有候选工作表：`name`、`header_row`、`data_rows`、`matched`、`matched_required`、`score` |
| `needs_sheet_choice` | 多个工作表都命中必需字段时为 `true`，应由用户确认 |
| `mapping` | 逐列明细：`source`、`target`、`target_label`、`confidence`、`method`、`status`、`candidates` |
| `conflicts` | 多列映射到同一字段的列名列表 |
| `ambiguous` | 匹配存在歧义的列名列表 |
| `unmapped_columns` | 未识别的列名列表 |

`method` 取值：`exact`（别名完全命中）、`contains`（包含关系）、`fuzzy`（相似度 ≥ 0.82）、`manual`（用户指定）、`none`。
`status` 取值：`matched`、`ambiguous`、`conflict`、`unmatched`。

### 8.4 `POST /imports/{batch_id}/remap`

用户调整工作表、表头行或映射后重新解析，**不需要重新上传文件**。

```json
{
  "sheet_name": "康养护理学院",
  "header_row": 1,
  "mapping": { "学生编号": "student_no", "备注": null }
}
```

三个字段都可省略：省略时沿用上一次保存的值。若希望丢弃旧映射、重新自动识别，传 `"mapping": {}`。

响应结构与 `preview` 一致。批次状态会被重置为 `uploaded`（缺必需字段时为 `failed`），已产生的异常明细清空。

### 8.5 映射的保存位置

映射与暂存文件同目录，文件名为 `<批次号>.mapping.json`，包含 `sheet_name`、`header_row`、`mapping`。
**未新增数据库字段**，避免改动已跑通的表结构；该文件与暂存文件同生命周期，提交成功后会一并删除。

### 8.6 行为约束

- 无论置信度多高，提交前都必须展示映射结果。
- 必填字段缺失或存在映射冲突时，`validate` 与 `commit` 均被禁止。
- 字段映射只解决列名差异，不改变数据校验规则：非法枚举、重复学号、日期错误照常报错。

---

## 9. 内部请求认证（可选，默认关闭）

| 开关 | 行为 |
|---|---|
| `INTERNAL_AUTH_ENABLED=false`（默认） | 与历史行为一致；`PUT /students/{no}` 不注册（同路径 GET 存在 → 405） |
| `INTERNAL_AUTH_ENABLED=true` | 所有业务路由要求 `X-Internal-*` 签名；`PUT` 注册；`X-Actor` 被忽略 |

- 公开端点：`GET /health`（liveness，仅 `{"status":"ok"}`）、`GET /health/ready`（数据库就绪，503 时不暴露细节）。
- 错误码：401（缺头/摘要不符/时间戳越界/签名错误）、403（权限不足/缺学院声明/导入接口非管理员）、409（nonce 重放）。
- **PR-C 前的临时限制**：7 个导入接口仅允许管理员；非管理员即使持有全部 `import:batch:*` 也返回 403。
- 完整规范（14 段 canonical、11 个头、金标向量）见 `docs/INTERNAL-AUTH-SPEC.md`。
