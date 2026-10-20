# 数据字典

面向业务人员的字段与取值说明。页面展示使用「中文名称」列，不直接暴露数据库字段名。

---

## 1. 学生信息（`campus.students`）

| 中文名称 | 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|---|
| 学号 | `student_no` | varchar(32) | 是 | 唯一；自动去除首尾空格；不可全空 |
| 姓名 | `student_name` | varchar(100) | 是 | 不可全空 |
| 学院 | `college_name` | varchar(100) | 否 | — |
| 专业 | `major_name` | varchar(100) | 否 | — |
| 班级 | `class_name` | varchar(100) | 否 | — |
| 入学年份 | `enrollment_year` | smallint | 否 | 1990–2100 |
| 在校状态 | `student_status` | varchar(20) | 是 | 见 3.1，默认「在校」 |
| 是否有效 | `is_active` | boolean | 是 | 默认 true；停用后默认列表不展示 |
| 创建时间 | `created_at` | timestamptz | 是 | 自动 |
| 更新时间 | `updated_at` | timestamptz | 是 | 每次修改自动刷新 |

> 系统不采集身份证号、手机号、家庭住址、家庭成员信息。

## 2. 学籍异动（`campus.student_changes`）

| 中文名称 | 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|---|
| 所属学生 | `student_id` | bigint | 是 | 外键，必须存在于学生表 |
| 异动类型 | `change_type` | varchar(30) | 是 | 见 3.2 |
| 生效日期 | `effective_date` | date | 是 | 1990-01-01 至 2100-12-31 |
| 异动原因 | `change_reason` | varchar(500) | 否 | 避免录入不必要敏感信息 |
| 记录状态 | `record_status` | varchar(20) | 是 | 见 3.3，默认「草稿」 |
| 来源批次 | `source_batch_id` | bigint | 否 | 导入时自动写入 |
| 原始行号 | `source_row_number` | integer | 否 | 导入时自动写入，用于追溯 |

## 3. 受控取值

### 3.1 在校状态 `student_status`

| 页面显示 | 代码 |
|---|---|
| 在校 | `enrolled` |
| 休学 | `suspended` |
| 退学 | `withdrawn` |
| 毕业 | `graduated` |
| 其他 | `other` |

### 3.2 异动类型 `change_type`

| 页面显示 | 代码 |
|---|---|
| 休学 | `suspend` |
| 复学 | `resume` |
| 退学 | `withdraw` |
| 转专业 | `transfer_major` |
| 转学 | `transfer_school` |
| 保留学籍 | `retain` |
| 其他 | `other` |

### 3.3 记录状态 `record_status`

| 页面显示 | 代码 | 含义 |
|---|---|---|
| 草稿 | `draft` | 尚未提交 |
| 待复核 | `pending_review` | 等待业务人员确认 |
| 已确认 | `confirmed` | 本工具内确认，**不代表学校审批通过** |
| 已退回 | `returned` | 需补充或修正 |

### 3.4 批次状态 `batch_status`

| 代码 | 含义 |
|---|---|
| `uploaded` | 已上传待校验 |
| `validated` | 校验完成，可提交 |
| `imported` | 已提交入库 |
| `failed` | 上传即失败（如缺必需列） |

### 3.5 异常状态 `issue_status`

| 代码 | 含义 |
|---|---|
| `open` | 待处理 |
| `resolved` | 已处理 |
| `needs_review` | 需业务确认 |

> 标记状态只影响跟踪，**不能**绕过必填与唯一性校验。

## 4. 异常代码

见 `docs/IMPORT-API.md` 第 4 节，共 8 类：`MISSING_REQUIRED`、`VALUE_TOO_LONG`、`INVALID_ENUM`、`INVALID_DATE`、`DUPLICATE_STUDENT_NO`、`UNKNOWN_STUDENT`、`DUPLICATE_BATCH`、`COLUMN_MAPPING_REQUIRED`。

## 5. 审计字段（`campus.operation_logs`）

| 字段 | 含义 |
|---|---|
| `actor_user_id` | 操作人标识；由受控后端在同一事务注入。为空表示无法识别到人 |
| `actor_db_role` | 实际登录的数据库角色（`session_user`） |
| `action` | `insert` / `update` / `delete` |
| `object_type` | 表名 |
| `object_id` | 记录主键 |
| `changed_fields` | 本次变更涉及的字段名 |
| `before_data` / `after_data` | 变更前后值（已剔除敏感字段） |
| `result` | `success` / `failed` |

## 6. 导入模板

| 模板 | 必需列 | 可选列 |
|---|---|---|
| 学生信息 | 学号、姓名 | 学院、专业、班级、入学年份、在校状态 |
| 学籍异动 | 学号、异动类型、生效日期 | 异动原因、记录状态 |

可选列缺失时按默认值处理（在校状态=在校，记录状态=草稿），不报错。
