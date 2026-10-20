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
| 身份 | 请求头 `X-Actor`，写入 `operation_logs.actor_user_id`。**阶段 1 未经认证**，仅用于演示审计链路 |
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
{"status": "ok", "database": "ok", "version": "0.1.0"}
```

数据库不可用时返回 **503**，不谎报健康。

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
