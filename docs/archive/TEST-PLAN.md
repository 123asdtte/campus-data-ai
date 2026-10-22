# 验收测试记录

**执行时间：** 2026-10-20 15:40–16:00（本地，虚构数据）
**环境：** Docker Engine 29.2.0 / Compose v5.0.2，PostgreSQL 16.15，Appsmith v2.5.0，Import API 0.1.0

结论：数据库层与导入闭环全部通过；Appsmith 页面尚未搭建，页面级用例（AT-011 / AT-012）保持待验；Dify 相关用例属阶段 2。

---

## 1. 结果总览

| ID | 场景 | 结果 | 证据 |
|---|---|---|---|
| AT-001 | 环境启动 | **PASS** | 三容器 `healthy`；`/api/v1/health` 返回 `All systems are up` |
| AT-002 | 学生新增 | **PASS（数据库层）** | `campus_app` 插入 `TESTCRUD001`，返回 id=221；页面待搭 |
| AT-003 | 学号唯一 | **PASS** | 重复插入被 `students_student_no_key` 拒绝 |
| AT-004 | 学生编辑 | **PASS** | `UPDATE 1`，`updated_at` 自动更新，审计 `changed_fields={class_name,updated_at}` |
| AT-005 | 学生停用 | **PASS** | `is_active=false` 生效，异动历史保留 |
| AT-006 | 异动关联 | **PASS** | `INSERT ... SELECT ... WHERE student_no='NOT_EXIST_999'` → `INSERT 0 0` |
| AT-007 | 正常导入 | **PASS** | `students_clean.xlsx` 10 行：10 有效 / 0 异常，提交写入 10 条，总数 210→220 |
| AT-008 | 异常校验 | **PASS** | 15 行样例识别 5 类异常，详见第 2 节 |
| AT-009 | 失败回滚 | **PASS** | 撤销 INSERT 权限后提交返回 500「已整体回滚」，学生数 221→221，批次状态仍为 `validated` |
| AT-010 | 重复文件 | **PASS** | 同 `file_sha256` 再上传，返回 `DUPLICATE_BATCH`（warning），不自动写入 |
| AT-011 | 筛选分页 | **待验** | SQL 已提供（`docs/APPSMITH-SETUP.md`），页面未搭建 |
| AT-012 | 导出 | **待验** | 依赖 Table 组件，页面未搭建 |
| AT-013 | Dify 正常调用 | **N/A** | 阶段 2 |
| AT-014 | Dify 中断 | **N/A** | 阶段 2；非 AI 功能不依赖 Dify，架构上已隔离 |
| AT-015 | 密钥保护 | **部分 PASS** | `.env` 已 gitignore，代码无硬编码；页面源码核查待页面完成 |
| AT-016 | 数据恢复 | **PASS** | 备份 24 KB，独立库恢复后计数一致（见第 3 节） |
| AT-017 | 网络边界 | **PASS** | 三个端口均绑定 `127.0.0.1`，无 `0.0.0.0` 映射 |
| AT-018 | 数据安全闸门 | **PASS** | 全库虚构数据；未部署 Dify，无业务库直连凭证 |

---

## 2. AT-008 异常识别明细

学生信息（`students_demo.xlsx`，15 行 / 有效 10 / 异常 5）：

| 行号 | 异常代码 | 字段 | 触发原因 |
|---|---|---|---|
| 12 | `MISSING_REQUIRED` | student_name | 姓名为空 |
| 13 | `DUPLICATE_STUDENT_NO` | student_no | 与第 2 行学号重复 |
| 14 | `INVALID_ENUM` | enrollment_year | 入学年份为「两千二四」 |
| 15 | `INVALID_ENUM` | student_status | 在校状态为「在读」（不在受控值） |
| 16 | `VALUE_TOO_LONG` | student_name | 姓名 105 字符（上限 100） |

学籍异动（`student_changes_demo.xlsx`，9 行 / 有效 5 / 异常 4）：

| 行号 | 异常代码 | 字段 | 触发原因 |
|---|---|---|---|
| 7 | `UNKNOWN_STUDENT` | student_no | `DEMO9999999999` 不在学生表 |
| 8 | `INVALID_DATE` | effective_date | `2026-13-45` |
| 9 | `INVALID_ENUM` | change_type | 「出国」不在受控值 |
| 10 | `MISSING_REQUIRED` | student_no | 学号为空 |

补充验证：仅含「编号 / 名字」两列的文件，批次直接置 `failed`，返回 `COLUMN_MAPPING_REQUIRED: 缺少必需列：学号, 姓名`。

---

## 3. AT-016 恢复演练

```text
备份：./scripts/backup.sh → backups/campus_20261020_155950.sql.gz（24 KB）
恢复：CREATE DATABASE campus_drill → gunzip | psql（ON_ERROR_STOP=1，无错误）
核对：students=221  changes=305  batches=9  issues=33  logs=530
     与生产库一致；演练库已 DROP
```

选择独立库而非覆盖生产库，目的是在不破坏当前环境的前提下验证 dump 可还原性。覆盖式恢复脚本 `scripts/restore.sh` 已提供，需输入库名二次确认。

---

## 4. 幂等与并发

| 用例 | 结果 |
|---|---|
| 同一批次重复 `commit` | 第二次返回 **409**「批次状态为 imported，不能提交」，未重复写入 |
| 提交时学号已存在 | `ON CONFLICT DO NOTHING` + 写入 `DUPLICATE_STUDENT_NO`（warning），计数为 skipped |
| 已导入批次再次 `validate` | 返回 **409** |

---

## 5. 遗留项

1. Appsmith 十个页面未搭建 —— 属人工步骤，配置见 `docs/APPSMITH-SETUP.md`。
2. 页面级越权测试（AT-015 完整版）需在页面完成后执行。
3. Dify 接入与 AI 相关验收在阶段 2 补充。
4. `X-Actor` 未经认证，正式试点前必须替换为受控身份（见 `docs/SECURITY-CHECKLIST.md`）。
