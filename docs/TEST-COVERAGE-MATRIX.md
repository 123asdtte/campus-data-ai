# import-api 测试覆盖矩阵

> **2026-10-22 更新（PR-E）**：现行用例总数为 **关闭态 130 passed / 开启态 116 passed**（另 101 skipped、1 xfailed）；本矩阵正文是 `c28ec94` 的 112 用例基线，缺口描述已部分被 PR-A/B/C/E 关闭，详见 `PR-E-ACCEPTANCE-REPORT.md`。
>
> Issue #8 第一步交付物（盘点，不改任何测试代码）。
> 基线：`main` @ `c28ec94`；用例数统计口径：`grep -c "def test_"` + 参数化展开，共 **112 个用例**（111 passed / 1 xfailed）。
> 盘点方式：逐行比对 7 个测试文件与 `import-api/app/` 全部源码，对照本矩阵 7 类场景。
> 用例位置统一记为 `文件名::类名::用例名`，省略 `import-api/tests/` 前缀。

## 0. 现有测试资产

| 文件 | 用例数 | 覆盖层 |
|---|---|---|
| `test_mapping.py` | 23 | 纯函数：表头规范化、别名索引、自动映射、手动覆盖、必需字段 |
| `test_parsing.py` | 17 | 纯函数：工作簿分析、表头定位、多工作表、重名列、编码 |
| `test_validation.py` | 29 | 纯函数：归一化、枚举编码、类型预转换、Pandera 结构校验、异常码映射 |
| `test_business_rules.py` | 10 | 纯函数：文件内重复、库内已存在、异动引用存在性 |
| `test_api_contract.py` | 19（含 1 xfail） | HTTP 契约：入参校验、错误码，不触达数据库 |
| `test_db_integration.py` | 14 | 真库：全链路、状态机、幂等、审计、行号偏移 |
| `conftest.py` | — | 夹具：`samples/` 读取、`api_client`、`db_session`/`clean_db`/`db_client` |

夹具：`samples/` 12 个文件。盘点时 **`test_conflict_columns.csv`、`bad_headers.xlsx`、`students_demo.xlsx` 零引用**（前者仅出现在 `docs/archive/IMPORT-MAPPING-TEST.md` 手工场景 7）；**§12 已全部纳入自动化用例**。

---

## 1. 批次状态机（`uploaded → validated → imported`）

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 未校验直接 commit → 409 | `test_db_integration.py::TestFullImportFlow::test_未校验直接提交返回409` | 有 | 断言含「不能提交」 |
| 已导入批次再 commit → 409 且不重复写 | `test_db_integration.py::TestFullImportFlow::test_重复提交返回409且不新增数据` | 有 | 同时断言 students 表仍为 2 行 |
| 已导入批次再 validate → 409 | `test_db_integration.py::TestFullImportFlow::test_已导入的批次不能再次校验` | 有 | — |
| 批次不存在 → 404 | `test_db_integration.py::TestFullImportFlow::test_不存在的批次返回404` | 有 | 只走了 validate 入口；commit / remap / get 的 404 是同函数不同入口，未逐个固定 |
| failed 批次（缺必需列）validate → 422 | `test_db_integration.py::TestRejectPaths::test_缺必需列时校验返回422` | 有 | 同时固定了预览返回 `status=failed` |
| failed 批次直接 commit | — | 无 | 落入 `service.py:721`「批次状态为 failed，不能提交」409 分支。与「未校验直接提交」同一分支但初始状态不同，值得单独固定，防止未来按状态细分逻辑时回归 |
| imported 批次 remap → 409 | — | 无 | `remap_batch` 有专门检查（`service.py:554`「该批次已导入，不能再调整映射」），无测试 |
| validated 批次 remap 后状态回退为 uploaded | — | 无 | remap 会把 `valid_rows/invalid_rows` 清零、状态打回 `uploaded`（`service.py:584-592`）。「校验 → remap → 再 commit 被拒」这条链无测试，而它是前端「改完映射重新校验」流程的必经路径 |
| 两个并行 uploaded 批次互不干扰 | — | 部分 | `test_同一文件再次上传给出警告但不阻断` 只验证了 imported 之后的重复上传；未验证同一文件两个未完成批次互不影响（各自 remap/validate 不串数据） |

## 2. 幂等

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 同文件重复上传 → warning 不阻断 | `test_db_integration.py::TestDuplicateBatchWarning::test_同一文件再次上传给出警告但不阻断` | 有 | 断言 `DUPLICATE_BATCH` 且预览 200 |
| 重复 commit → 409 | `test_db_integration.py::TestFullImportFlow::test_重复提交返回409且不新增数据` | 有 | — |
| 重复导入不产生重复行 | `test_db_integration.py::TestDuplicateBatchWarning::test_重复导入同一批学生不会产生重复行` | 部分 | 第二批次实际走的是「校验阶段学号已存在 → 整行判 invalid → 提交时整体排除」（`inserted=0, invalid_rows_excluded=2`）。**commit 逐行 `ON CONFLICT DO NOTHING` 的 skipped 分支没有被走到**（`service.py:752-763`：写 `DUPLICATE_STUDENT_NO` warning、计入 `skipped_rows`） |
| commit 时单行已存在（校验后、提交前被外部写入） | — | 无 | 构造：先 validate 通过，再用直连 SQL 插入同学号，再 commit。这是 `ON CONFLICT` 分支的唯一入口，也是「提交阶段重新校验」设计要点的实际承压点 |
| student_changes 提交时学生不存在 → skipped | — | 无 | `service.py:786-787`。构造：异动批次 validate 通过后删掉学生再 commit。注意 validate 的 `UNKNOWN_STUDENT` 是 error，所以同样必须「校验后删除」才能走到 |
| batch_code 唯一性 | — | 无 | `IMP-时间戳-token_hex(3)`，同秒并发理论上可撞。可 monkeypatch 掉时间与随机源连传两次断言不同。低优先级 |

## 3. 异常文件

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 空文件 → 400 | `test_api_contract.py::TestPreviewValidation::test_空文件返回400` | 有 | — |
| 仅表头无数据 → 400 | `test_api_contract.py::TestPreviewValidation::test_只有表头没有数据行返回400` | 有 | 只覆盖 CSV；xlsx 空工作表是同一条代码路径，未覆盖 |
| 超体积 → 413 | `test_api_contract.py::TestPreviewValidation::test_超过大小上限返回413` | 部分 | 用 `monkeypatch` 把 `max_upload_mb` 置 0 的等价类；真实 10MB 边界（=10MB 通过 / +1 字节拒绝）未测 |
| 非 Excel/CSV 扩展名 | — | 无 | **行为与直觉相反**：活代码路径（`parsing.load_frame`）只按 `_is_xlsx` 二分，`.txt` 等后缀会被当 CSV 解析——内容是 CSV 就能正常导入（`create_batch:389` 还把暂存后缀兜底成 `.csv`）。`service.py:_read_frame` 里那句「仅支持 .xlsx / .csv」是不可达的死代码。扩展名白名单实际未生效，无测试固定该行为 |
| 损坏的 xlsx（扩展名对、内容是垃圾字节） | — | 无 | `analyze_workbook` → `openpyxl.load_workbook` 抛出的不是 `ServiceError`，会冒到 FastAPI 变成 **500**。现状未定义，补测前建议先开 issue 定行为（预期 400） |
| 缺表头（无任何命中列） | `test_parsing.py::TestAnalyzeWorkbook::test_没有可用表头时返回空` | 部分 | 只覆盖纯函数分析层；API 层行为未固定——`load_frame` 会退回 `header=1`，最终返回 200 + `status=failed` + 缺少必需列，而不是 400 |
| CSV 编码无法识别 | — | 无 | **同样与死代码有关**：`parsing.load_frame:182-186` 用 `errors="replace"` 静默替换，非法字节变成 U+FFFD 后照常入库（学号变乱码），不会报错；`_read_frame:62-70` 的「三编码全失败 → ServiceError」不可达。GBK 正常路径已有 `test_gbk编码的csv可读`，静默替换行为无测试 |
| `.xlsm` 后缀 | — | 无 | `_is_xlsx` / `create_batch` / `_read_frame` 都显式支持 `.xlsm`，无测试 |

## 4. 字段映射

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 别名精确匹配 | `test_mapping.py::TestAutoMap::test_标准表头全部精确匹配`、`test_中文别名变体`、`test_列顺序变化不影响映射` | 有 | 含 `method/confidence/status` 全字段断言 |
| 包含关系命中 | `test_mapping.py::TestAutoMap::test_包含关系命中并标注方法` | 有 | 断言 0.78 与 `method=contains` |
| 冲突列 | `test_mapping.py::TestAutoMap::test_同一字段被多列命中时后者标为冲突` | 有 | — |
| 未知列不强行分配 | `test_mapping.py::TestAutoMap::test_未知列不强行分配`、`test_空列名不产生匹配` | 有 | — |
| 手动 remap 覆盖（纯函数层） | `test_mapping.py::TestApplyOverrides`（3 例） | 有 | 含「接管已占用字段后原列解除占用」「置空忽略」「未知来源忽略」 |
| API 层 remap（`POST /imports/{id}/remap`） | — | 无 | 整个接口无测试：mapping 重映射、切换 `sheet_name`/`header_row`、remap 后 missing → failed、remap 已导入批次 409、remap 不存在批次 404 |
| remap 后重新校验 | — | 无 | issue 点名场景。链路：preview → remap(改 mapping) → validate → 断言按新映射出的结果。`_write_sidecar`/`_read_sidecar` 也仅能经此链路间接覆盖，目前零覆盖 |
| ambiguous（歧义）状态 | — | 无 | `parsing.py:259` 的 `AMBIGUITY_GAP` 逻辑与 `_mapping_payload` 的 `ambiguous` 字段无任何用例。构造例：列名「学院专业」同时 contains 命中 college/major（均 0.78）→ `status=ambiguous` |
| fuzzy（模糊）方法 | — | 无 | difflib ≥0.82 分支（`parsing.py:236-238`）无用例，`method="fuzzy"` 从未被断言。构造例：拼错的英文表头 `studnt_no` 对 `student_no` ratio≈0.94 |
| 已存在但零引用的夹具 | — | 无 | `samples/test_conflict_columns.csv`、`bad_headers.xlsx`、`students_demo.xlsx`。冲突场景目前只靠内存构造列名覆盖，缺「夹具上传 → 冲突提示 → 手动指定 → 冲突解除」的 API 层端到端用例 |

## 5. 校验失败

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 必填缺失（结构层） | `test_validation.py::TestStructuralIssues::test_缺姓名报缺失并定位到行`、`test_学号为空报缺失`、`test_异动表缺学号报缺失` | 有 | 含 `severity=error` 断言 |
| 必填缺失（API/DB 层行号） | `test_db_integration.py::TestRowNumberOffset::test_缺姓名的行报Excel第6行` | 有 | 预览行号与校验行号都带偏移 |
| 类型错误 | `test_validation.py::TestPreCoerceStudents::test_非数字年份报错并置空`、`test_小数年份报错`；`TestPreCoerceChanges::test_无法识别的日期报INVALID_DATE` | 有 | 同时断言置空与 issue_code |
| 枚举非法 | `test_validation.py::TestStructuralIssues::test_非法在校状态报错`、`test_入学年份超范围报错` | 有 | — |
| 行号偏移（表头不在第 1 行） | `test_validation.py::TestPreCoerceStudents::test_行号随表头偏移`、`TestStructuralIssues::test_缺姓名时行号带表头偏移`、`TestBusinessRules`（business_rules）`test_行号带表头偏移`；DB 层 `test_缺姓名的行报Excel第6行` | 有 | 三个校验层 + DB 层都有 |
| 同行同列重复异常只报一次 | `test_validation.py::TestStructuralIssues::test_同一行同一列的重复异常只报一次` | 有 | — |
| 一个单元格出错不掩盖其他问题 | `test_db_integration.py::TestRejectPaths::test_脏数据样例同时报出四类异常`、`test_一个单元格出错不掩盖同批次其他问题` | 有 | 四类异常叠加 + 逐行定位 |
| `change_reason` 超 500 字 | — | 无 | `CHANGE_SCHEMA` 有 500 上限（`schemas.py:42`），无用例 |
| 500 条 issues 截断 | — | 无 | `validate_batch` 返回 `issues[:500]`、`get_batch` SQL `LIMIT 500`。构造 600 行全缺姓名的批次可同时验证截断与 `error_count` 仍准确 |
| warning 不计入 invalid_rows | — | 部分 | `_row_has_error` 只数 error 行，目前仅由 `test_重复导入同一批学生不会产生重复行` 间接体现（2 行 error → excluded=2）；「error 与 warning 混合在同一批次」无直接断言 |

## 6. 事务

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 审计与业务同事务、操作人正确 | `test_db_integration.py::TestAuditTrail::test_提交后写入审计且操作人正确` | 有 | 断言 `actor_user_id=ci.tester` 且 2 行 insert 全记录 |
| 操作人来自请求头而非数据库账号 | `test_db_integration.py::TestAuditTrail::test_操作人来自请求头而非数据库账号` | 有 | 断言 actors 集合恰为 `{other.actor}` |
| commit 中途失败整体回滚 | — | 无 | `main.py:195-200` 的 `DatabaseError` → 500「已整体回滚」分支无测试。可先 validate，再用直连 SQL 制造 INSERT 失败（如临时 revoke 测试角色权限）触达 |
| 失败后批次状态保持 validated | — | 无 | 回滚后 `UPDATE ... batch_status='imported'` 应一并回滚。与上一条是同一个测试，未覆盖意味着「失败后批次卡在 imported」这种脏状态无法被现有测试发现 |
| 校验与提交之间暂存文件被替换 | — | 无 | `service.py` 设计要点 2「提交阶段重新校验一遍，防止校验与提交之间文件被替换」——这条防线本身无测试。构造：preview 后向 `staged_path` 同一路径写入不同内容，再 commit，断言结果以新内容为准 |
| 暂存文件丢失 → 409 | — | 无 | `_revalidate:506` 与 `remap:558` 的「暂存文件已不存在，请重新上传」。删掉暂存文件后 validate / remap 应 409 |

## 7. 清理（临时文件 / 上传目录）

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| commit 成功后删暂存文件、`staged_path` 置 NULL | — | 无 | `service.py:794-805`（`keep_upload_files=False` 时 `os.remove` + 更新 DB）。无任何用例断言文件系统与 DB 字段，即「导入成功但文件永远留在上传目录」这类回归发现不了 |
| sidecar 映射文件随批次清理 | — | 无 | **缺陷（非仅缺口）**：commit 只删 `staged_path`，`{batch_code}.mapping.json` 从不删除，每次成功导入都永久残留一个文件。建议第二步先开 issue 再修，不要在补测时顺手改业务代码 |
| 失败路径（上传后从不 commit）的残留 | — | 无 | 没有 TTL / 孤儿清理机制，属设计缺口。测试只能固定现状（断言孤儿文件存在），不建议固化；应推动增加清理任务后再说 |
| 测试自身卫生 | — | 无 | `conftest.py` 的 `UPLOAD_DIR` 用 `tempfile.mkdtemp()` 创建但不删除。CI 容器内无感，本地反复跑会攒目录 |

---

## 8. 七类之外的重要空白

| 场景 | 现有用例 | 覆盖状态 | 缺口说明 |
|---|---|---|---|
| 只读查询行为（`queries.py` 4 个函数） | `test_api_contract.py::TestQueryValidation::test_查询参数越界返回422` 等 | 部分 | 只有 422 参数校验。`list_students` 的分页/过滤/排序、`get_student` 的 404 与 changes 关联、`get_filters`、`get_overview` 全部零行为覆盖——而它们是 React 前端正在读的接口 |
| `GET /imports`、`GET /imports/{id}` | — | 无 | 批次列表与详情无测试。现有 DB 用例都从 preview 响应里拿 `batch_id`，查询接口本身（含 `list_batches` 的 limit 夹紧）未验证 |
| `preview-base64` 成功路径 | `test_api_contract.py::TestBase64Preview`（2 个失败 400） | 部分 | `_decode_base64` 的 `data:` URL 前缀剥离、空白剔除、宽松兜底分支无覆盖 |
| 经 API 传 mapping overrides | — | 无 | multipart preview 与 preview-base64 都接受 `mapping` 参数，无 API 层用例（纯函数层有） |
| `_read_frame` / `_map_columns` 死代码 | — | 无 | `service.py:57` 与 `:84` 两个函数无调用方、无测试。容易被误读为「已覆盖」，建议开 issue 删除 |
| 中文操作人经 `X-Actor` 传递 | `test_api_contract.py::TestActorHeader::test_中文操作人无法通过X_Actor传递` | 有（xfail 固化缺陷） | 已知缺陷已用 `xfail(strict=True)` 固化；修复后必须移除标记，让用例转为正式断言 |

---

## 9. 统计与第二步建议

| 覆盖状态 | §1–§7 七类场景 | §8 七类之外 | 合计 |
|---|---|---|---|
| 有 | 23 | 1 | 24 |
| 部分 | 5 | 2 | 7 |
| 无 | 25 | 3 | 28 |
| **合计** | **53** | **6** | **59** |

按「风险 × 成本」排序的补测顺序（供第二步执行，本 PR 不动测试代码）：

1. **remap 接口 + remap 后重新校验**（§4）——前端核心流程完全无保护，且能一并覆盖 sidecar
2. **暂存文件生命周期**（§6/§7）——「校验后文件被替换」「成功后文件不删」都直指设计要点，其中 sidecar 残留需先开 issue
3. **commit 的 ON CONFLICT / skipped 分支**（§2）——幂等的真正承压点，现在只测了「整体排除」那条轻松的路
4. **异常文件的 API 层行为**（§3）——尤其「损坏 xlsx 变 500」，建议先定行为再补测
5. **只读查询层**（§8）——React 前端依赖，零行为覆盖，但需要真库、成本中等
6. 其余单点（ambiguous/fuzzy、500 截断、batch_code、`.xlsm`、编码全失败）按需取

不纳入第二步的事项：死代码删除（开 issue）、孤儿文件清理机制（开 issue）、中文操作人修复（开 issue，与安全整改的权限设计相关）。

## 10. 盘点中暴露的疑似缺陷（需单独开 issue，不在本 PR 修）

按 issue #8 边界「不修改业务代码，除非测试/盘点暴露真实缺陷，需单独开 Issue 说明」：

> 其中第 1、2、3、5 条属于「先定行为再补测」，四张决策单见
> [`TEST-BEHAVIOR-DECISIONS.md`](TEST-BEHAVIOR-DECISIONS.md)（D-1 ~ D-4，含选项、成本与验证方式）。
> **第 1、2、3、5 条均已实施**（D-1 ~ D-4），第 4 条（损坏 xlsx 应 400）随 D-3 一并修掉；
> 第 6 条（#23）已由 PR-C 修复，对应 xfail 已转为正式断言。

| # | 发现 | 位置 | 建议 |
|---|---|---|---|
| 1 | sidecar 映射文件从不清理，每次成功导入永久残留一个 `.mapping.json` | `service.py` 的 `commit_batch` 清理段 | **已修复**：`_remove_staged()` 同时删暂存文件与 sidecar；孤儿文件的一次性清理脚本仍在 D-1 范围内未做 |
| 2 | 扩展名白名单未生效：`.txt` 等内容为 CSV 的文件可正常导入（相关报错在死代码里） | `service.py` 的 `create_batch` 入口 | **已修复**：`_require_supported_extension()` 按 `.xlsx/.xlsm/.csv` 白名单拒绝，「格式不对」与「内容为空」不再是同一句提示 |
| 3 | 编码非法时静默替换为 U+FFFD，乱码学号可入库 | `parsing.py` 的 `_read_raw_rows` / `load_frame` | **已修复**：`_decode_text()` 严格解码；**实测发现比「替换字符」更严重的问题**——旧实现先用 UTF-8 解一份、再用 GBK 严格解一次并覆盖，`学号,姓名\n2026001,\n` 这类「中文表头 + ASCII 数据」的 UTF-8 文件整份恰好能被 GBK 解出，表头变成「瀛﹀彿,濮撳悕」，映射全失配后表现为「200 + failed / 缺少必需列」 |
| 4 | 损坏的 xlsx 返回 500 而非 400 | `parsing.py` 的 `_open_workbook` | **已修复**：openpyxl / pandas 的异常统一收成 `parsing.WorkbookError`，由 `service._prepare` 转 `ServiceError`（400） |
| 5 | `_read_frame` / `_map_columns` 为死代码 | `service.py`（原 `:57`、`:84`） | **已删除**（D-4），随之移除未使用的 `import io` |
| 6 | ~~**缺少「入学年份」等可选列时提交 500**~~：`_pre_coerce` 把该列转成 `Int64`，缺失值是 pandas 的 `pd.NA`，`commit_batch` 直接交给 psycopg 报 `cannot adapt type 'NAType'` 并整体回滚 | `service.py:116`、`:733-751` | **已修复（PR-C）**：取值统一经 `_cell()` 把 `pd.NA`/`NaT` 归一成 `None`；`TestOptionalColumn` 与 `TestConflictFixture` 已转为正式断言 |

---

## 11. 第二步补测（2026-10-22）

按 §9 的排序补齐，只补「无」和「部分」，不重复已有用例。新增 5 个文件、37 个用例。

| 新增文件 | 层 | 用例数 | 补的缺口 |
|---|---|---|---|
| `test_remap.py` | 真库 | 8 | §4 remap 接口（此前整接口零行为测试）：改映射后预览/列映射同步、手动指定解除原占用列、取消必需列转 failed、校验后 remap 状态回退 `uploaded`、回退后必须重新校验、已导入批次 409、并行批次互不干扰 |
| `test_staging.py` | 真库 + 纯 FS | 7 | §6/§7 暂存文件生命周期：预览/校验后必须保留、提交后删除且 `staged_path` 置空、`keep_upload_files` 为真时保留、文件被外部删除后 409；sidecar 残留（§10-1，已修复并转为正式断言） |
| `test_commit_conflict.py` | 真库 | 3 | §2 ON CONFLICT 分支（见下方新发现） |
| `test_queries_read.py` | 真库 | 11 | §8 只读查询层（此前零行为覆盖）：分页与总数、参数夹取、keyword ILIKE、学院筛选与 `forced_college` 取交集、`get_student` 异动排序 |
| `test_parsing_edge.py` | 纯函数 | 8 | §3 解析边界：后缀白名单（§10-2）、严格解码（§10-3）、损坏 xlsx（§10-4）、sidecar 读写往返与损坏兜底 |

### 新发现（补测过程中确认，不在本轮修）

**`commit_batch` 的 ON CONFLICT / `skipped_rows` 分支在正常流程下不可达。**

`commit_batch` 在 INSERT 之前会调 `_revalidate` 重算业务问题，同学号会被判
`DUPLICATE_STUDENT_NO`（severity=error）从而在循环里被 `continue` 掉，根本到不了
`INSERT ... ON CONFLICT`。串行导入走的是 `invalid_rows_excluded`，不是 `skipped_rows`。

`ON CONFLICT` 实际是**并发兜底**：只有「校验完成后、提交开始前」被另一个事务插入同学号
时才会命中。`test_commit_conflict.py` 用 monkeypatch 让 `_fetch_known_students` 返回空集
来模拟这个窗口，另设一条用例固化正常路径，避免有人误以为 `skipped_rows` 是常规可达路径。

这条同时意味着：§2「幂等」的承压点不在 ON CONFLICT，而在提交前的二次校验——后者现在有测试了。

**remap 无法永久取消某一列的映射。**

sidecar 只保存正向映射（源列 → 目标字段）。把某列 overrides 置空后，当次响应会正确
报 `missing_required` 并把批次标成 `failed`，但下次解析时 `auto_map` 会把它重新占用，
校验照样通过。也就是说「忽略这一列」这个意图没有落盘，用户改不掉自动映射的结果。
已由 `test_remap.py::test_取消必需列映射只在当次响应生效` 固化为现状。

### 仍未覆盖（按 §9 顺序，建议后续处理）

1. ~~异常文件的 **API 层**行为~~ → §12 已补
2. ~~`get_overview` / `get_filters`~~ → §12 已补
3. ~~`samples/` 中 `bad_headers.xlsx`、`students_demo.xlsx` 仍零引用~~ → §12 已补
4. ~~§10-2、§10-3、§10-5 三项（扩展名白名单、编码替换、死代码）需先定行为再补测~~
   → 决策单：[`TEST-BEHAVIOR-DECISIONS.md`](TEST-BEHAVIOR-DECISIONS.md) D-2 / D-3 / D-4，**均已实施**
5. §10-1 的「存量孤儿 sidecar 一次性清理脚本」——待定放哪个目录（与 #3 的运维脚本规划相关）
6. §10-6（#23，缺可选列提交 500）——已定案未修，合并 #22 时一并处理

---

## 12. 第三步补测（2026-10-22）

补 §11「仍未覆盖」的第 1、2、3 项，并顺带补掉 §4 的夹具缺口。新增 1 个文件、14 个用例，
全部是真库用例（`CAMPUS_TEST_DATABASE_URL` 未设置时跳过）。

| 类 | 用例数 | 补的缺口 |
|---|---|---|
| `TestMetaFilters` | 3 | `GET /meta/filters` 从零行为覆盖到：学院/班级去重、停用学生剔除、空库零值 |
| `TestOverview` | 3 | `GET /stats/overview`：`students_active` 与 `students_total` 口径差异、`pending_review`、`change_type_counts` 排序、`recent_batches` 最多 5 条且最新在前、空库边界 |
| `TestAbnormalFileOverHttp` | 5 | §3 在 HTTP 层：坏表头、仅表头 xlsx、未知后缀、`.xlsm`、损坏 xlsx |
| `TestConflictFixture` | 2 | §4 冲突场景端到端：`test_conflict_columns.csv` 上传 → 冲突提示 → 手动指定解除 → 提交成功（#23 已由 PR-C 修复） |
| `TestDemoFixture` | 1 | `students_demo.xlsx` 的文档口径（15 行 / 10 有效 / 5 异常）变成可执行断言 |

### 新发现

**`bad_headers.xlsx` 不会触发「缺少必需列」。** 这份夹具的表头是「编号 / 名字」，
其中「名字」按别名精确命中 `student_name`，「编号」靠 contains 模糊命中 `student_no`
（置信度 0.78），于是表头明显不规范的名单被 `status=uploaded` 正常接收，用户收不到任何提示。
现状已由 `test_meta_and_files.py::TestAbnormalFileOverHttp::test_无可识别表头被包含匹配接受`
固化；是否要给 contains 命中加 warning，需先定行为（并入 §10 的待定项一起评估）。

**#23 的第二个复现入口：`test_conflict_columns.csv`。** 这份夹具同样没有「入学年份」列，
当时「冲突 → 手动指定 → 校验通过 → 提交」在提交环节 500（`cannot adapt type 'NAType'`），
与 #23 完全同因。**PR-C 已修复**：`_cell()` 统一归一 `pd.NA/NaT`，该用例已转为正式断言；
这也说明 #23 不是某份样例的偶发问题，而是所有缺可选列的名单都会踩到。

### 口径说明

`recent_batches` 的「最新在前」不能靠 `preview` 连续调用来验证：同一测试里的多次写入
落在同一事务瞬间，`created_at` 完全相同，断言顺序等于赌数据库物理行序。用例显式把
`created_at` 改写成按 `id` 递增的时间戳后再断言，结论才是确定的。

