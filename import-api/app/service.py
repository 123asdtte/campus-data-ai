"""导入业务服务：解析 → 映射 → 校验 → 事务提交。

设计要点：
1. 解析与校验全部在服务端完成，页面不承担数据规则。
2. 提交阶段重新校验一遍，防止校验与提交之间文件被替换。
3. 幂等：批次状态从 validated 到 imported 的条件更新是唯一入口，
   重复提交只会命中一次，不会重复写入学生数据。
4. 操作人身份通过 set_config('campus.actor_user_id') 注入同一事务，
   审计触发器据此记录 actor_user_id。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from . import parsing
from .config import settings
from .db import pool
from .mapping import (
    CHANGE_TYPE_MAP,
    ENUM_FIELDS,
    RECORD_STATUS_MAP,
    STUDENT_STATUS_MAP,
    TARGETS,
)
from .models import Issue
from .schemas import SCHEMAS

MAX_TEXT_ISSUE_ROW = 1  # 批次级问题的行号占位（数据库要求 >= 1）


class ServiceError(Exception):
    """可映射为 4xx 的业务异常。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------------ 工具
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _set_actor(cur, actor: str) -> None:
    cur.execute("SELECT set_config('campus.actor_user_id', %s, true)", (actor,))


def _read_frame(data: bytes, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), dtype=str, engine="openpyxl", keep_default_na=False)
    if lower.endswith(".csv"):
        last_error: Optional[Exception] = None
        for encoding in ("utf-8-sig", "gbk", "utf-8"):
            try:
                return pd.read_csv(
                    io.BytesIO(data), dtype=str, encoding=encoding, keep_default_na=False
                )
            except UnicodeDecodeError as exc:  # 尝试下一种编码
                last_error = exc
        raise ServiceError(f"CSV 编码无法识别，请另存为 UTF-8：{last_error}")
    raise ServiceError("仅支持 .xlsx / .csv 文件")


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\u3000", " ").strip() for c in df.columns]
    df = df.reset_index(drop=True)
    # 空字符串统一视为缺失，便于必填判断
    for col in df.columns:
        df[col] = df[col].map(lambda v: None if isinstance(v, str) and v.strip() == "" else (v.strip() if isinstance(v, str) else v))
    return df


def _map_columns(df: pd.DataFrame, target: str) -> Tuple[pd.DataFrame, List[str], Dict[str, str]]:
    spec = TARGETS[target]
    aliases: Dict[str, str] = spec["aliases"]  # type: ignore[assignment]
    mapping: Dict[str, str] = {}
    used: set[str] = set()
    for col in df.columns:
        canonical = aliases.get(col)
        if canonical and canonical not in used:
            mapping[col] = canonical
            used.add(canonical)

    missing = [field for field in spec["required"] if field not in used]  # type: ignore[union-attr]

    # 补齐可选列，保证后续校验与插入结构稳定
    for field in spec["fields"]:  # type: ignore[union-attr]
        if field not in used and field not in mapping.values():
            df[field] = None

    renamed = df.rename(columns=mapping)
    keep = [f for f in spec["fields"] if f in renamed.columns]  # type: ignore[union-attr]
    return renamed[keep], missing, mapping


def _encode_enums(df: pd.DataFrame) -> pd.DataFrame:
    for field, (mapping, _codes) in ENUM_FIELDS.items():
        if field in df.columns:
            df[field] = df[field].map(
                lambda v: mapping.get(str(v).strip(), v) if v is not None else None
            )
    return df


def _pre_coerce(df: pd.DataFrame, target: str, row_offset: int = 0) -> Tuple[pd.DataFrame, List[Issue]]:
    """类型预转换：无法转换的值在此登记为问题，避免库层抛出不可读异常。"""
    issues: List[Issue] = []

    if "enrollment_year" in df.columns:
        values: List[Optional[int]] = []
        for idx, raw in df["enrollment_year"].items():
            row_no = idx + 2 + row_offset
            if raw is None:
                values.append(None)
                continue
            try:
                number = float(str(raw).strip())
            except (TypeError, ValueError):
                issues.append(Issue(row_no, "INVALID_ENUM", "入学年份必须是数字", "enrollment_year"))
                values.append(None)
                continue
            if number != int(number):
                issues.append(Issue(row_no, "INVALID_ENUM", "入学年份必须是整数", "enrollment_year"))
                values.append(None)
                continue
            values.append(int(number))
        df["enrollment_year"] = pd.array(values, dtype="Int64")

    if target == "student_changes" and "effective_date" in df.columns:
        raw_series = df["effective_date"]
        parsed = pd.to_datetime(raw_series, errors="coerce", format="mixed")
        for idx, raw in raw_series.items():
            row_no = idx + 2 + row_offset
            if raw is None:
                issues.append(Issue(row_no, "MISSING_REQUIRED", "生效日期为必填项", "effective_date"))
            elif pd.isna(parsed.loc[idx]):
                issues.append(Issue(row_no, "INVALID_DATE", f"生效日期无法识别：{raw}", "effective_date"))
        df["effective_date"] = parsed

    # 枚举为空时落默认值（与数据库默认保持一致）
    if target == "students" and "student_status" in df.columns:
        df["student_status"] = df["student_status"].map(
            lambda v: STUDENT_STATUS_MAP.get(str(v).strip(), v) if v is not None else "enrolled"
        )
    if target == "student_changes" and "record_status" in df.columns:
        df["record_status"] = df["record_status"].map(
            lambda v: RECORD_STATUS_MAP.get(str(v).strip(), v) if v is not None else "draft"
        )

    return df, issues


def _code_for_failure(check: str, column: str, is_missing: bool) -> str:
    if is_missing:
        return "MISSING_REQUIRED"
    text = str(check)
    if "str_length" in text:
        return "VALUE_TOO_LONG"
    if column == "effective_date":
        return "INVALID_DATE"
    return "INVALID_ENUM"


def _structural_issues(df: pd.DataFrame, target: str, row_offset: int = 0) -> List[Issue]:
    """Pandera 结构校验：必填、类型、长度、枚举、数值范围。"""
    schema = SCHEMAS[target]
    try:
        schema.validate(df, lazy=True)
        return []
    except Exception as exc:  # pandera SchemaErrors 及其子类
        failure_cases = getattr(exc, "failure_cases", None)
        if failure_cases is None or len(failure_cases) == 0:
            return [Issue(MAX_TEXT_ISSUE_ROW, "INVALID_ENUM", f"结构校验失败：{exc}")]

        issues: List[Issue] = []
        seen: set[tuple] = set()
        for record in failure_cases.to_dict("records"):
            index = record.get("index")
            column = record.get("column")
            check = record.get("check")
            value = record.get("failure_case")
            if index is None or pd.isna(index):
                issues.append(
                    Issue(MAX_TEXT_ISSUE_ROW, _code_for_failure(check, str(column), False),
                          f"{column} 校验失败：{value}", str(column) if column else None)
                )
                continue
            row_no = int(index) + 2 + row_offset
            is_missing = value is None or (isinstance(value, float) and pd.isna(value)) or value == ""
            if (row_no, column) in seen:
                continue
            seen.add((row_no, column))
            code = _code_for_failure(check, str(column), is_missing)
            message = "该字段为必填项" if is_missing else f"取值不符合要求：{value}"
            issues.append(Issue(row_no, code, message, str(column) if column else None))
        return issues


def _business_issues(
    df: pd.DataFrame, target: str, known_students: set[str], row_offset: int = 0
) -> List[Issue]:
    """业务规则：仅处理 Pandera 覆盖不到的部分。"""
    issues: List[Issue] = []

    if "student_no" in df.columns:
        codes = df["student_no"]

        # 同一学生在一次学籍异动导入中出现多条是正常业务场景，
        # 只有学生信息导入才要求学号在文件内唯一。
        if target == "students":
            duplicated = codes[codes.notna() & codes.duplicated(keep="first")]
            for idx in duplicated.index:
                issues.append(
                    Issue(idx + 2 + row_offset, "DUPLICATE_STUDENT_NO", f"学号在文件内重复：{df.at[idx, 'student_no']}", "student_no")
                )
            for idx, value in codes.items():
                if value is not None and value in known_students:
                    issues.append(
                        Issue(idx + 2 + row_offset, "DUPLICATE_STUDENT_NO", f"学号已存在于数据库：{value}", "student_no")
                    )
        else:
            for idx, value in codes.items():
                if value is not None and value not in known_students:
                    issues.append(
                        Issue(idx + 2 + row_offset, "UNKNOWN_STUDENT", f"数据库中不存在该学号：{value}", "student_no")
                    )

    return issues


def _fetch_known_students(cur, student_numbers: List[str]) -> set[str]:
    cleaned = [s for s in {str(v) for v in student_numbers if v}]
    if not cleaned:
        return set()
    cur.execute(
        "SELECT student_no FROM campus.students WHERE student_no = ANY(%s)",
        (cleaned,),
    )
    return {row["student_no"] for row in cur.fetchall()}


def _row_has_error(issues: List[Issue]) -> set[int]:
    return {issue.row_number for issue in issues if issue.severity == "error"}


def _cell(value: Any) -> Any:
    """把 pandas/numpy 标量转成可 JSON 序列化的值。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value


def _insert_issues(cur, batch_id: int, issues: List[Issue]) -> None:
    if not issues:
        return
    cur.executemany(
        """
        INSERT INTO campus.import_issues
            (batch_id, row_number, field_name, issue_code, severity, issue_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [(batch_id, *issue.as_tuple()) for issue in issues],
    )


# ------------------------------------------------------------------ 映射持久化
def _sidecar_path(staged_path: str) -> str:
    return f"{os.path.splitext(staged_path)[0]}.mapping.json"


def _write_sidecar(staged_path: str, payload: Dict[str, Any]) -> None:
    """把工作表、表头行与列映射存到暂存文件旁边。

    不新增数据库字段，避免动已跑通的表结构；映射与文件同生共死。
    """
    try:
        with open(_sidecar_path(staged_path), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    except OSError:
        pass


def _read_sidecar(staged_path: str) -> Dict[str, Any]:
    path = _sidecar_path(staged_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _apply_mapping(frame: pd.DataFrame, matches: List[Any], target: str) -> pd.DataFrame:
    rename: Dict[str, str] = {}
    used: set[str] = set()
    for item in matches:
        if item.target and item.source in frame.columns and item.target not in used:
            rename[item.source] = item.target
            used.add(item.target)

    output = frame[list(rename)].rename(columns=rename) if rename else pd.DataFrame(index=frame.index)
    for field in TARGETS[target]["fields"]:  # type: ignore[index]
        if field not in output.columns:
            output[field] = None
    return output[list(TARGETS[target]["fields"])]  # type: ignore[index]


def _prepare(
    data: bytes,
    filename: str,
    target: str,
    sheet_name: Optional[str],
    header_row: Optional[int],
    overrides: Optional[Dict[str, Optional[str]]],
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Any], List[str], Dict[str, Any]]:
    frame, info = parsing.load_frame(data, filename, target, sheet_name, header_row)
    frame = _normalize_frame(frame)
    matches = parsing.auto_map(frame.columns, target)
    if overrides:
        matches = parsing.apply_overrides(matches, overrides)
    missing = parsing.required_missing(matches, target)
    mapped = _apply_mapping(frame, matches, target)
    return frame, mapped, matches, missing, info


def _mapping_payload(matches: List[Any], target: str) -> Dict[str, Any]:
    return {
        "mapping": parsing.matches_as_list(matches, target),
        "column_mapping": parsing.mapping_to_dict(matches),
        "unmapped_columns": [m.source for m in matches if not m.target and m.status == "unmatched"],
        "conflicts": [m.source for m in matches if m.status == "conflict"],
        "ambiguous": [m.source for m in matches if m.status == "ambiguous"],
    }


# ------------------------------------------------------------------ 主流程
def create_batch(
    data: bytes,
    filename: str,
    target_type: str,
    actor: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    overrides: Optional[Dict[str, Optional[str]]] = None,
    created_dept_id: Optional[int] = None,
) -> Dict[str, Any]:
    if target_type not in TARGETS:
        raise ServiceError(f"不支持的目标类型：{target_type}")
    if not data:
        raise ServiceError("上传文件为空")
    if len(data) > settings.max_upload_bytes:
        raise ServiceError(f"文件超过 {settings.max_upload_mb} MB 上限", 413)

    safe_name = os.path.basename(filename)
    digest = _sha256(data)
    frame_raw, mapped, matches, missing, info = _prepare(
        data, filename, target_type, sheet_name, header_row, overrides
    )

    if len(mapped) == 0:
        raise ServiceError("文件没有可导入的数据行")
    if len(mapped) > settings.max_rows:
        raise ServiceError(f"数据行数 {len(mapped)} 超过 {settings.max_rows} 行上限", 413)

    batch_code = f"IMP-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3).upper()}"
    ext = ".xlsx" if safe_name.lower().endswith((".xlsx", ".xlsm")) else ".csv"
    staged_path = os.path.join(settings.upload_dir, f"{batch_code}{ext}")
    os.makedirs(settings.upload_dir, exist_ok=True)
    with open(staged_path, "wb") as handle:
        handle.write(data)

    _write_sidecar(
        staged_path,
        {
            "sheet_name": info["sheet_name"],
            "header_row": info["header_row"],
            "mapping": parsing.mapping_to_dict(matches),
        },
    )

    issues: List[Issue] = []
    status = "uploaded"
    if missing:
        labels = ", ".join(TARGETS[target_type]["labels"][f] for f in missing)  # type: ignore[index]
        issues.append(
            Issue(
                MAX_TEXT_ISSUE_ROW,
                "COLUMN_MAPPING_REQUIRED",
                f"缺少必需列：{labels}",
                None,
            )
        )
        status = "failed"

    with pool.connection() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor)
            cur.execute(
                "SELECT id FROM campus.import_batches WHERE file_sha256 = %s AND batch_status = 'imported' LIMIT 1",
                (digest,),
            )
            duplicate = cur.fetchone()
            if duplicate:
                issues.append(
                    Issue(MAX_TEXT_ISSUE_ROW, "DUPLICATE_BATCH", "该文件此前已导入过，请确认是否需要重复导入")
                )
                issues[-1].severity = "warning"

            cur.execute(
                """
                INSERT INTO campus.import_batches
                    (batch_code, source_filename, file_sha256, target_type, total_rows,
                     batch_status, staged_path, created_by, failure_reason, created_dept_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    batch_code,
                    safe_name[:255],
                    digest,
                    target_type,
                    len(mapped),
                    status,
                    staged_path,
                    actor[:150],
                    "缺少必需列" if missing else None,
                    created_dept_id,
                ),
            )
            batch_id = cur.fetchone()["id"]

            _insert_issues(cur, batch_id, issues)
            # 首次解析的异常也写一条摘要，保持“每次重写都有摘要”的一致性
            cur.execute("SELECT campus.record_import_issues(%s, 'preview')", (batch_id,))

    preview_rows = []
    for idx, row in mapped.head(20).iterrows():
        item = {"__row": int(info["header_row"]) + idx + 1}
        for field in TARGETS[target_type]["fields"]:  # type: ignore[index]
            item[field] = _cell(row.get(field))
        preview_rows.append(item)

    mapping_payload = _mapping_payload(matches, target_type)

    return {
        "batch_id": batch_id,
        "batch_code": batch_code,
        "target_type": target_type,
        "status": status,
        "total_rows": len(mapped),
        "sheet_name": info["sheet_name"],
        "header_row": info["header_row"],
        "sheets": info["analysis"]["sheets"],
        "needs_sheet_choice": info["analysis"]["needs_sheet_choice"],
        "missing_required": missing,
        "column_mapping": mapping_payload["column_mapping"],
        "mapping": mapping_payload["mapping"],
        "unmapped_columns": mapping_payload["unmapped_columns"],
        "conflicts": mapping_payload["conflicts"],
        "ambiguous": mapping_payload["ambiguous"],
        "field_labels": TARGETS[target_type]["labels"],  # type: ignore[index]
        "preview": preview_rows,
        "issues": [
            {
                "row_number": i.row_number,
                "field_name": i.field_name,
                "issue_code": i.issue_code,
                "severity": i.severity,
                "issue_message": i.issue_message,
            }
            for i in issues
        ],
    }


def _load_batch(cur, batch_id: int) -> Dict[str, Any]:
    cur.execute("SELECT * FROM campus.import_batches WHERE id = %s", (batch_id,))
    row = cur.fetchone()
    if row is None:
        raise ServiceError(f"导入批次不存在：{batch_id}", 404)
    return row


def _assert_batch_scope(batch: Dict[str, Any], dept_id: Optional[int]) -> None:
    """批次级授权：非管理员只能访问本部门创建的批次。

    dept_id 为 None 表示管理员/关闭态全范围；批次没有归属（历史 NULL）
    时仅管理员可见，避免历史批次被任意学院读取。
    """
    if dept_id is None:
        return
    owner = batch.get("created_dept_id")
    if owner is None or int(owner) != int(dept_id):
        raise ServiceError("无权访问该导入批次", 403)


def _revalidate(cur, batch: Dict[str, Any]) -> Tuple[pd.DataFrame, List[Issue], Dict[str, str]]:
    path = batch.get("staged_path")
    if not path or not os.path.exists(path):
        raise ServiceError("暂存文件已不存在，请重新上传", 409)

    with open(path, "rb") as handle:
        data = handle.read()

    target = batch["target_type"]
    meta = _read_sidecar(path)
    _frame_raw, mapped, matches, missing, info = _prepare(
        data,
        batch["source_filename"],
        target,
        meta.get("sheet_name"),
        meta.get("header_row"),
        meta.get("mapping"),
    )

    if missing:
        labels = ", ".join(TARGETS[target]["labels"][f] for f in missing)  # type: ignore[index]
        raise ServiceError(f"缺少必需列：{labels}", 422)

    # 表头不在第 1 行时，问题行号需要整体后移，否则定位会错
    offset = max(int(info["header_row"]) - 1, 0)
    mapped = _encode_enums(mapped)
    mapped, issues = _pre_coerce(mapped, target, offset)
    issues.extend(_structural_issues(mapped, target, offset))

    known = _fetch_known_students(cur, mapped["student_no"].tolist() if "student_no" in mapped else [])
    issues.extend(_business_issues(mapped, target, known, offset))
    mapped.attrs["row_offset"] = offset
    return mapped, issues, parsing.mapping_to_dict(matches)


def remap_batch(
    batch_id: int,
    actor: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    overrides: Optional[Dict[str, Optional[str]]] = None,
    dept_id: Optional[int] = None,
) -> Dict[str, Any]:
    """用户调整工作表/表头/列映射后重新解析，不重新上传文件。"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor)
            cur.execute("SELECT * FROM campus.import_batches WHERE id = %s FOR UPDATE", (batch_id,))
            batch = cur.fetchone()
            if batch is None:
                raise ServiceError(f"导入批次不存在：{batch_id}", 404)
            _assert_batch_scope(batch, dept_id)
            if batch["batch_status"] == "imported":
                raise ServiceError("该批次已导入，不能再调整映射", 409)

            path = batch.get("staged_path")
            if not path or not os.path.exists(path):
                raise ServiceError("暂存文件已不存在，请重新上传", 409)

            with open(path, "rb") as handle:
                data = handle.read()

            target = batch["target_type"]
            meta = _read_sidecar(path)
            use_sheet = sheet_name or meta.get("sheet_name")
            use_header = header_row or meta.get("header_row")
            use_mapping = overrides if overrides is not None else meta.get("mapping")

            _frame_raw, mapped, matches, missing, info = _prepare(
                data, batch["source_filename"], target, use_sheet, use_header, use_mapping
            )

            _write_sidecar(
                path,
                {
                    "sheet_name": info["sheet_name"],
                    "header_row": info["header_row"],
                    "mapping": parsing.mapping_to_dict(matches),
                },
            )

            status = "failed" if missing else "uploaded"
            cur.execute(
                """
                UPDATE campus.import_batches
                   SET total_rows = %s, valid_rows = 0, invalid_rows = 0,
                       batch_status = %s, failure_reason = %s, finished_at = NULL
                 WHERE id = %s
                """,
                (len(mapped), status, "缺少必需列" if missing else None, batch_id),
            )
            # 删除收口：旧明细只能经受控函数删除，函数内先写摘要再删
            cur.execute("SELECT campus.clear_import_issues(%s, 'remap')", (batch_id,))

            issues: List[Issue] = []
            if missing:
                labels = ", ".join(TARGETS[target]["labels"][f] for f in missing)  # type: ignore[index]
                issues.append(
                    Issue(MAX_TEXT_ISSUE_ROW, "COLUMN_MAPPING_REQUIRED", f"缺少必需列：{labels}")
                )
                _insert_issues(cur, batch_id, issues)
            # 每次重写都留一条摘要，包括“重写后 0 条异常”
            cur.execute("SELECT campus.record_import_issues(%s, 'remap')", (batch_id,))

    preview_rows = []
    for idx, row in mapped.head(20).iterrows():
        item = {"__row": int(info["header_row"]) + idx + 1}
        for field in TARGETS[target]["fields"]:  # type: ignore[index]
            item[field] = _cell(row.get(field))
        preview_rows.append(item)

    mapping_payload = _mapping_payload(matches, target)
    return {
        "batch_id": batch_id,
        "batch_code": batch["batch_code"],
        "target_type": target,
        "status": status,
        "total_rows": len(mapped),
        "sheet_name": info["sheet_name"],
        "header_row": info["header_row"],
        "sheets": info["analysis"]["sheets"],
        "needs_sheet_choice": info["analysis"]["needs_sheet_choice"],
        "missing_required": missing,
        "column_mapping": mapping_payload["column_mapping"],
        "mapping": mapping_payload["mapping"],
        "unmapped_columns": mapping_payload["unmapped_columns"],
        "conflicts": mapping_payload["conflicts"],
        "ambiguous": mapping_payload["ambiguous"],
        "field_labels": TARGETS[target]["labels"],  # type: ignore[index]
        "preview": preview_rows,
        "issues": [
            {
                "row_number": i.row_number,
                "field_name": i.field_name,
                "issue_code": i.issue_code,
                "severity": i.severity,
                "issue_message": i.issue_message,
            }
            for i in issues
        ],
    }


def validate_batch(batch_id: int, actor: str, dept_id: Optional[int] = None) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor)
            cur.execute("SELECT * FROM campus.import_batches WHERE id = %s FOR UPDATE", (batch_id,))
            batch = cur.fetchone()
            if batch is None:
                raise ServiceError(f"导入批次不存在：{batch_id}", 404)
            _assert_batch_scope(batch, dept_id)
            if batch["batch_status"] == "imported":
                raise ServiceError("该批次已导入，不能再次校验", 409)

            mapped, issues, mapping = _revalidate(cur, batch)

            # 删除收口 + 重写后摘要（两条摘要，均只有一行，不再是逐行噪声）
            cur.execute("SELECT campus.clear_import_issues(%s, 'validate')", (batch_id,))
            _insert_issues(cur, batch_id, issues)
            cur.execute("SELECT campus.record_import_issues(%s, 'validate')", (batch_id,))

            error_rows = _row_has_error(issues)
            total = len(mapped)
            invalid = len(error_rows)
            valid = total - invalid

            cur.execute(
                """
                UPDATE campus.import_batches
                   SET batch_status = 'validated', total_rows = %s, valid_rows = %s, invalid_rows = %s
                 WHERE id = %s
                """,
                (total, valid, invalid, batch_id),
            )

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    return {
        "batch_id": batch_id,
        "batch_code": batch["batch_code"],
        "status": "validated",
        "total_rows": total,
        "valid_rows": valid,
        "invalid_rows": invalid,
        "error_count": error_count,
        "warning_count": warning_count,
        "column_mapping": mapping,
        "issues": [
            {
                "row_number": i.row_number,
                "field_name": i.field_name,
                "issue_code": i.issue_code,
                "severity": i.severity,
                "issue_message": i.issue_message,
            }
            for i in issues[:500]
        ],
    }


def commit_batch(
    batch_id: int,
    actor: str,
    dept_id: Optional[int] = None,
    allowed_colleges: Optional[set[str]] = None,
) -> Dict[str, Any]:
    inserted = 0
    skipped: List[Dict[str, Any]] = []

    with pool.connection() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor)

            # 先锁定并校验状态/归属，再更新；任一步失败都整体回滚
            cur.execute("SELECT * FROM campus.import_batches WHERE id = %s FOR UPDATE", (batch_id,))
            batch = cur.fetchone()
            if batch is None:
                raise ServiceError(f"导入批次不存在：{batch_id}", 404)
            if batch["batch_status"] != "validated":
                raise ServiceError(
                    f"批次状态为 {batch['batch_status']}，不能提交（可能已提交或未校验）", 409
                )
            _assert_batch_scope(batch, dept_id)

            target = batch["target_type"]
            mapped, issues, _mapping = _revalidate(cur, batch)
            error_rows = _row_has_error(issues)
            row_offset = int(mapped.attrs.get("row_offset", 0))

            # 逐行学院授权：非管理员只能提交签名声明学院内的数据；
            # 发现越权行时整批拒绝，不执行任何写入。
            if allowed_colleges is not None:
                out_of_scope = []
                for idx, row in mapped.iterrows():
                    row_no = idx + 2 + row_offset
                    if row_no in error_rows:
                        continue
                    college = (row.get("college_name") or "").strip()
                    if not college or college not in allowed_colleges:
                        out_of_scope.append(row_no)
                if out_of_scope:
                    raise ServiceError(
                        f"批次包含 {len(out_of_scope)} 行越权学院数据，已整批拒绝且未写入", 403
                    )

            cur.execute(
                """
                UPDATE campus.import_batches
                   SET batch_status = 'imported', finished_at = now()
                 WHERE id = %s AND batch_status = 'validated'
                """,
                (batch_id,),
            )

            for idx, row in mapped.iterrows():
                row_no = idx + 2 + row_offset
                if row_no in error_rows:
                    continue

                if target == "students":
                    cur.execute(
                        """
                        INSERT INTO campus.students
                            (student_no, student_name, college_name, major_name, class_name,
                             enrollment_year, student_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (student_no) DO NOTHING
                        """,
                        (
                            _cell(row["student_no"]),
                            _cell(row["student_name"]),
                            _cell(row.get("college_name")),
                            _cell(row.get("major_name")),
                            _cell(row.get("class_name")),
                            _cell(row.get("enrollment_year")),
                            _cell(row.get("student_status")) or "enrolled",
                        ),
                    )
                    if cur.rowcount == 1:
                        inserted += 1
                    else:
                        skipped.append({"row_number": row_no, "reason": "学号已存在，未写入"})
                        cur.execute(
                            """
                            INSERT INTO campus.import_issues
                                (batch_id, row_number, field_name, issue_code, severity, issue_message)
                            VALUES (%s, %s, 'student_no', 'DUPLICATE_STUDENT_NO', 'warning', %s)
                            """,
                            (batch_id, row_no, f"提交时学号已存在，已跳过：{row['student_no']}"),
                        )
                else:
                    cur.execute(
                        """
                        INSERT INTO campus.student_changes
                            (student_id, change_type, effective_date, change_reason,
                             record_status, source_batch_id, source_row_number)
                        SELECT s.id, %s, %s, %s, %s, %s, %s
                          FROM campus.students s
                         WHERE s.student_no = %s
                        """,
                        (
                            row["change_type"],
                            row.get("effective_date"),
                            row.get("change_reason"),
                            row.get("record_status") or "draft",
                            batch_id,
                            row_no,
                            row["student_no"],
                        ),
                    )
                    if cur.rowcount == 1:
                        inserted += 1
                    else:
                        skipped.append({"row_number": row_no, "reason": "学生不存在，未写入"})

            if skipped:
                # 提交阶段新增的重复学号警告同样只写一条摘要
                cur.execute("SELECT campus.record_import_issues(%s, 'commit')", (batch_id,))

            cur.execute(
                "UPDATE campus.import_batches SET valid_rows = %s, invalid_rows = %s WHERE id = %s",
                (inserted, batch["total_rows"] - inserted, batch_id),
            )

    if not settings.keep_upload_files:
        path = batch.get("staged_path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE campus.import_batches SET staged_path = NULL WHERE id = %s", (batch_id,)
                )

    return {
        "batch_id": batch_id,
        "batch_code": batch["batch_code"],
        "status": "imported",
        "inserted_rows": inserted,
        "skipped_rows": skipped,
        "invalid_rows_excluded": batch["total_rows"] - inserted - len(skipped),
    }


def get_batch(batch_id: int, dept_id: Optional[int] = None) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            batch = _load_batch(cur, batch_id)
            _assert_batch_scope(batch, dept_id)
            cur.execute(
                """
                SELECT row_number, field_name, issue_code, severity, issue_message, issue_status
                  FROM campus.import_issues
                 WHERE batch_id = %s
                 ORDER BY row_number, id
                 LIMIT 500
                """,
                (batch_id,),
            )
            issue_rows = cur.fetchall()

    return {
        "batch_id": batch["id"],
        "batch_code": batch["batch_code"],
        "source_filename": batch["source_filename"],
        "target_type": batch["target_type"],
        "status": batch["batch_status"],
        "total_rows": batch["total_rows"],
        "valid_rows": batch["valid_rows"],
        "invalid_rows": batch["invalid_rows"],
        "created_by": batch["created_by"],
        "created_at": batch["created_at"].isoformat() if batch["created_at"] else None,
        "finished_at": batch["finished_at"].isoformat() if batch["finished_at"] else None,
        "issues": [
            {
                "row_number": r["row_number"],
                "field_name": r["field_name"],
                "issue_code": r["issue_code"],
                "severity": r["severity"],
                "issue_message": r["issue_message"],
                "issue_status": r["issue_status"],
            }
            for r in issue_rows
        ],
    }


def list_batches(limit: int = 50, dept_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, batch_code, source_filename, target_type, total_rows,
                       valid_rows, invalid_rows, batch_status, created_by, created_at
                  FROM campus.import_batches
                 WHERE (%s::bigint IS NULL OR created_dept_id = %s::bigint)
                 ORDER BY created_at DESC
                 LIMIT %s
                """,
                (dept_id, dept_id, min(max(limit, 1), 200)),
            )
            rows = cur.fetchall()
    return [
        {
            **{k: v for k, v in row.items() if k != "created_at"},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]
