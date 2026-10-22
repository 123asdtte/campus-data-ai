# Appsmith 页面搭建说明

Appsmith 页面无法用脚本自动生成，需在界面中按本文配置。以下 SQL 与绑定表达式均可直接粘贴。

---

## 1. 数据源（两个）

### 1.1 `campus-db`（PostgreSQL）

| 配置项 | 值 |
|---|---|
| Connection mode | Read / Write |
| Host address | `campus-db` |
| Port | `5432` |
| Database name | `campus` |
| Username | `campus_app` |
| Password | `.env` 中的 `APP_DB_PASSWORD` |
| SSL mode | Disabled（容器内网） |
| **Use Prepared Statement** | **开启（必须）** |

> 用 `campus-db` 而不是 `localhost`：Appsmith 与数据库在同一 Docker 网络内。
> 不要填 `campus_dba`，那是运维账号。

### 1.2 `campus-import`（REST API）

| 配置项 | 值 |
|---|---|
| URL | `http://import-api:8000` |
| Headers | `X-Actor: {{appsmith.user.email}}` |

该 Key 不含敏感凭据，仍建议只授予业务管理员使用。

---

## 2. 页面清单与查询

约定：`{{ }}` 为 Appsmith 绑定；所有用户输入均以参数形式传入，不做字符串拼接。

### UI-01 工作台首页

统计卡片（各自独立查询，避免一次拉全表）：

```sql
-- Q_StatStudents
SELECT count(*) AS total FROM campus.students WHERE is_active;
-- Q_StatChanges
SELECT count(*) AS total FROM campus.student_changes WHERE is_active;
-- Q_StatIssues
SELECT count(*) AS total FROM campus.import_issues WHERE issue_status = 'open' AND severity = 'error';
-- Q_LastBatch
SELECT batch_code, created_at, batch_status FROM campus.import_batches ORDER BY created_at DESC LIMIT 1;
```

环境标识：静态文本「本地测试 / 虚构数据」。

### UI-02 学生信息列表

```sql
-- Q_Students（分页 + 筛选）
SELECT id, student_no, student_name, college_name, major_name, class_name,
       enrollment_year, student_status, is_active, updated_at
FROM campus.students
WHERE is_active = {{SwitchShowInactive.isSwitchedOn}}
  AND ({{InputKeyword.text}} = ''
       OR student_no ILIKE '%' || {{InputKeyword.text}} || '%'
       OR student_name ILIKE '%' || {{InputKeyword.text}} || '%')
  AND ({{SelectCollege.selectedOptionValue}} = '' OR college_name = {{SelectCollege.selectedOptionValue}})
ORDER BY student_no
LIMIT {{TableStudents.pageSize}}
OFFSET {{(TableStudents.pageNo - 1) * TableStudents.pageSize}};

-- Q_StudentsCount（同条件，仅 count(*)）
```

组件：`Table`（服务端分页，每页 20/50/100）、`Input`（关键词）、`Select`（学院）、`Switch`（显示停用）、按钮「新增」「编辑」「停用」。

### UI-03 学生详情 / 编辑

```sql
-- Q_CreateStudent
INSERT INTO campus.students
  (student_no, student_name, college_name, major_name, class_name, enrollment_year, student_status)
VALUES
  ({{InputStudentNo.text}}, {{InputStudentName.text}}, {{InputCollege.text}},
   {{InputMajor.text}}, {{InputClass.text}},
   NULLIF({{InputYear.text}}, '')::smallint, {{SelectStatus.selectedOptionValue}})
RETURNING id;

-- Q_UpdateStudent
UPDATE campus.students
   SET student_no = {{InputStudentNo.text}},
       student_name = {{InputStudentName.text}},
       college_name = {{InputCollege.text}},
       major_name = {{InputMajor.text}},
       class_name = {{InputClass.text}},
       enrollment_year = NULLIF({{InputYear.text}}, '')::smallint,
       student_status = {{SelectStatus.selectedOptionValue}}
 WHERE id = {{TableStudents.selectedRow.id}};

-- Q_DeactivateStudent（逻辑停用，不提供物理删除）
UPDATE campus.students SET is_active = false WHERE id = {{TableStudents.selectedRow.id}};
```

学号重复时数据库返回唯一约束错误，页面需在 `onError` 中提示「学号已存在」。

### UI-04 学籍异动列表

```sql
-- Q_Changes（视图已关联学生姓名）
SELECT id, student_no, student_name, college_name, class_name,
       change_type, effective_date, record_status, is_active
FROM campus.v_student_changes
WHERE is_active = {{SwitchShowInactive.isSwitchedOn}}
  AND ({{SelectType.selectedOptionValue}} = '' OR change_type = {{SelectType.selectedOptionValue}})
  AND ({{DateFrom.selectedDate}} IS NULL OR effective_date >= {{DateFrom.selectedDate}})
  AND ({{DateTo.selectedDate}} IS NULL OR effective_date <= {{DateTo.selectedDate}})
ORDER BY effective_date DESC
LIMIT {{TableChanges.pageSize}}
OFFSET {{(TableChanges.pageNo - 1) * TableChanges.pageSize}};
```

### UI-05 异动表单

```sql
-- Q_CreateChange
INSERT INTO campus.student_changes
  (student_id, change_type, effective_date, change_reason, record_status)
SELECT id, {{SelectChangeType.selectedOptionValue}}, {{DateEffective.selectedDate}},
       {{InputReason.text}}, {{SelectRecordStatus.selectedOptionValue}}
  FROM campus.students
 WHERE student_no = {{InputStudentNo.text}} AND is_active;
```

`INSERT ... SELECT` 的写法保证：学号不存在时写入 0 行，不会产生孤儿异动。

### UI-06 导入向导

组件：`FilePicker`（限制 .xlsx/.csv）→ `Select`（目标类型）→ `Table`（预览）→ 按钮「校验」「确认导入」。

```text
Q_Preview  : POST {{campus-import.url}}/imports/preview-base64
             Body(JSON): {
               "filename": "{{FilePicker1.files[0].name}}",
               "content_base64": "{{FilePicker1.files[0].data}}",
               "target_type": "{{SelectTarget.selectedOptionValue}}"
             }

Q_Validate : POST {{campus-import.url}}/imports/{{Q_Preview.data.batch_id}}/validate
Q_Commit   : POST {{campus-import.url}}/imports/{{Q_Preview.data.batch_id}}/commit
Q_Batch    : GET  {{campus-import.url}}/imports/{{Q_Preview.data.batch_id}}
```

交互规则：
- `Q_Preview.data.status === 'failed'` 时禁用「校验」按钮，并展示 `issues`。
- 「确认导入」前必须已执行 `Q_Validate` 且 `valid_rows > 0`，并弹窗显示「有效 N 行 / 异常 M 行」。
- 提交成功后 `Q_Commit.data.status === 'imported'`，刷新 `Q_Students`。

### UI-07 导入批次与异常

```sql
-- Q_Batches
SELECT id, batch_code, source_filename, target_type, total_rows, valid_rows,
       invalid_rows, batch_status, created_by, created_at
FROM campus.import_batches ORDER BY created_at DESC LIMIT 50;

-- Q_Issues
SELECT row_number, field_name, issue_code, severity, issue_message, issue_status
FROM campus.import_issues
WHERE batch_id = {{TableBatches.selectedRow.id}}
ORDER BY row_number LIMIT 500;
```

### UI-08 统计报表

```sql
-- Q_StatByType
SELECT change_type, count(*) AS cnt FROM campus.student_changes
WHERE is_active GROUP BY change_type ORDER BY cnt DESC;

-- Q_StatByMonth
SELECT to_char(effective_date, 'YYYY-MM') AS month, count(*) AS cnt
FROM campus.student_changes WHERE is_active GROUP BY 1 ORDER BY 1;

-- Q_StatByCollege
SELECT s.college_name, count(*) AS cnt
FROM campus.student_changes c JOIN campus.students s ON s.id = c.student_id
WHERE c.is_active GROUP BY 1 ORDER BY cnt DESC;

-- Q_ExportRows（导出前确认记录数）
SELECT count(*) AS cnt FROM campus.v_student_changes
WHERE change_type = {{SelectType.selectedOptionValue}};
```

导出：使用 Table 组件内置 Download（CSV），字段由当前查询列决定。

### UI-09 AI 助手（阶段 2）

阶段 1 不实现。阶段 2 用 `Iframe` 组件嵌入 Dify WebApp 地址，不使用 API 调用。
若后续需要在导入报告中生成说明，则走 `Import API → Dify API` 的服务端调用，与 iframe 是两条独立路径。

### UI-10 系统说明

静态页面：版本号、镜像标签、端口表、当前环境（本地测试/虚构数据）、枚举字典（见 `docs/DATA-DICTIONARY.md`）、安全提示。

---

## 3. 角色配置（社区版限制）

Appsmith 社区版仅 3 个固定角色，无自定义角色、无字段级/行级权限、无审计日志：

| 角色 | 建议授予对象 | 实际可见范围 |
|---|---|---|
| Administrator | 系统管理员 | 全部 |
| Developer | 业务管理员 | 全部应用与数据源（**可改查询**） |
| App Viewer | 只读查看者 | 只能查看已发布应用，无法打开编辑器 |

因此「只读查看者无法导出未授权数据」**无法靠平台实现**，只能：
1. 单独发布一个只读应用（不含新增/编辑/导出按钮）；
2. 数据库侧使用 `campus_ro` 账号创建第二个数据源；
3. 真实数据接入前，改用受控 API 层做权限判定。

详见 `docs/SECURITY-CHECKLIST.md`。

---

## 4. 已知行为

- Appsmith 直连数据库时无法注入 `campus.actor_user_id`，审计日志只记录 `actor_db_role = campus_app`。这是阶段 1 的已知限制。
- Appsmith 的连接池会复用连接，**不要**用 `SET` 语句做会话级配置，行为不可预期。
- 所有写操作应通过页面按钮触发，并在成功后刷新对应查询。
