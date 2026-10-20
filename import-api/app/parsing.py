"""工作簿结构分析与字段自动映射。

职责：
1. 在多个工作表中找出最可能是业务数据的表，并定位表头行；
2. 把列名与字段别名做规范化匹配，给出置信度与方法；
3. 不做静默猜测——得分接近时返回多个候选，由调用方要求用户确认。

设计边界：
- 只负责“列名差异”，不校验数据内容是否合法（那是 schemas.py / service.py 的职责）。
- 不认识的列一律保留为未匹配，绝不强行分配字段。
"""
from __future__ import annotations

import csv
import difflib
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .mapping import TARGETS, build_alias_index, normalize_header

MAX_SCAN_ROWS = 15
FUZZY_THRESHOLD = 0.82
AMBIGUITY_GAP = 0.12


# ------------------------------------------------------------------ 规范化
# normalize_header 由 mapping.py 提供，保证别名表与匹配算法使用同一套规则。


@dataclass(slots=True)
class ColumnMatch:
    source: str
    target: Optional[str] = None
    confidence: float = 0.0
    method: str = "none"            # exact | contains | fuzzy | manual | none
    status: str = "unmatched"       # matched | ambiguous | conflict | unmatched
    candidates: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SheetCandidate:
    name: str
    header_row: int
    data_rows: int
    matched: int
    matched_required: int
    score: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "header_row": self.header_row,
            "data_rows": self.data_rows,
            "matched": self.matched,
            "matched_required": self.matched_required,
            "score": round(self.score, 3),
        }


# ------------------------------------------------------------------ 读取
def _is_xlsx(filename: str) -> bool:
    return filename.lower().endswith((".xlsx", ".xlsm"))


def _read_raw_rows(data: bytes, filename: str, sheet_name: Optional[str]) -> Tuple[List[List[Any]], int]:
    """读出原始行（不含表头处理），返回 (rows, total_rows)。"""
    if _is_xlsx(filename):
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            worksheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.worksheets[0]
            rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
            return rows, len(rows)
        finally:
            workbook.close()

    raw = data.decode("utf-8-sig", errors="replace")
    try:
        raw = data.decode("gbk")
    except UnicodeDecodeError:
        pass
    reader = list(csv.reader(io.StringIO(raw)))
    return [list(row) for row in reader], len(reader)


def _score_row(values: Sequence[Any], alias_index: Dict[str, str], required: set[str]) -> Tuple[int, int]:
    matched = 0
    matched_required = 0
    for cell in values:
        key = normalize_header(cell)
        if not key:
            continue
        target = alias_index.get(key)
        if target:
            matched += 1
            if target in required:
                matched_required += 1
    return matched, matched_required


def analyze_workbook(data: bytes, filename: str, target: str) -> Dict[str, Any]:
    """遍历工作表与前 15 行，找出候选表头。"""
    alias_index = build_alias_index(target)
    required = set(TARGETS[target]["required"])  # type: ignore[arg-type]

    sheet_names: List[str]
    if _is_xlsx(filename):
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet_names = list(workbook.sheetnames)
        workbook.close()
    else:
        sheet_names = ["CSV"]

    candidates: List[SheetCandidate] = []
    for name in sheet_names:
        rows, total = _read_raw_rows(data, filename, name)
        best: Optional[SheetCandidate] = None
        for index, row in enumerate(rows[:MAX_SCAN_ROWS]):
            matched, matched_required = _score_row(row, alias_index, required)
            if matched == 0:
                continue
            score = matched + matched_required * 2
            candidate = SheetCandidate(
                name=name,
                header_row=index + 1,
                data_rows=max(total - index - 1, 0),
                matched=matched,
                matched_required=matched_required,
                score=float(score),
            )
            if best is None or candidate.score > best.score:
                best = candidate
        if best is not None:
            candidates.append(best)

    candidates.sort(key=lambda item: (item.matched_required, item.score, item.data_rows), reverse=True)
    best = candidates[0] if candidates else None

    # 多个工作表都命中必需字段时，不静默选择，交给用户确认
    viable = [c for c in candidates if c.matched_required >= len(required) and c.data_rows > 0]
    needs_sheet_choice = len(viable) > 1

    return {
        "sheets": [c.as_dict() for c in candidates],
        "sheet_names": sheet_names,
        "best": best.as_dict() if best else None,
        "needs_sheet_choice": needs_sheet_choice,
    }


def load_frame(
    data: bytes,
    filename: str,
    target: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """按指定工作表与表头行载入数据；未指定时使用分析结果。"""
    analysis = analyze_workbook(data, filename, target)
    best = analysis["best"]

    chosen_sheet = sheet_name or (best["name"] if best else analysis["sheet_names"][0])
    chosen_header = header_row or (best["header_row"] if best else 1)

    if _is_xlsx(filename):
        frame = pd.read_excel(
            io.BytesIO(data),
            sheet_name=chosen_sheet,
            header=chosen_header - 1,
            dtype=str,
            engine="openpyxl",
            keep_default_na=False,
        )
    else:
        raw = data.decode("utf-8-sig", errors="replace")
        try:
            raw = data.decode("gbk")
        except UnicodeDecodeError:
            pass
        frame = pd.read_csv(io.StringIO(raw), header=chosen_header - 1, dtype=str, keep_default_na=False)

    # 表头可能重名（如两列都叫“备注”），补序号避免 pandas 取列时返回多列
    seen: Dict[str, int] = {}
    unique_columns: List[str] = []
    for column in frame.columns:
        name = str(column).replace("\u3000", " ").strip()
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        unique_columns.append(name)
    frame.columns = unique_columns

    # 去掉整行为空的行（表头下方常有空行）
    frame = frame.dropna(how="all").reset_index(drop=True)
    frame = frame.loc[:, [c for c in frame.columns if c and not str(c).startswith("Unnamed")]]

    info = {
        "sheet_name": chosen_sheet,
        "header_row": chosen_header,
        "data_rows": int(len(frame)),
        "analysis": analysis,
    }
    return frame, info


# ------------------------------------------------------------------ 匹配
def _best_candidates(column: str, alias_index: Dict[str, str]) -> List[Dict[str, Any]]:
    key = normalize_header(column)
    if not key:
        return []

    hits: Dict[str, Tuple[float, str]] = {}

    def bump(target: str, confidence: float, method: str) -> None:
        current = hits.get(target)
        if current is None or confidence > current[0]:
            hits[target] = (confidence, method)

    exact = alias_index.get(key)
    if exact:
        bump(exact, 1.0, "exact")
    else:
        for alias, target in alias_index.items():
            if len(alias) >= 2 and (alias in key or key in alias):
                bump(target, 0.78, "contains")
            else:
                ratio = difflib.SequenceMatcher(None, key, alias).ratio()
                if ratio >= FUZZY_THRESHOLD:
                    bump(target, round(ratio, 2), "fuzzy")

    ranked = sorted(hits.items(), key=lambda item: item[1][0], reverse=True)
    return [
        {"field": target, "confidence": confidence, "method": method}
        for target, (confidence, method) in ranked[:3]
    ]


def auto_map(columns: Iterable[str], target: str) -> List[ColumnMatch]:
    """为每一列给出最优匹配，并标注歧义与冲突。"""
    alias_index = build_alias_index(target)
    matches: List[ColumnMatch] = []

    for column in columns:
        candidates = _best_candidates(str(column), alias_index)
        if not candidates:
            matches.append(ColumnMatch(source=str(column)))
            continue

        top = candidates[0]
        ambiguous = len(candidates) > 1 and (top["confidence"] - candidates[1]["confidence"]) < AMBIGUITY_GAP
        matches.append(
            ColumnMatch(
                source=str(column),
                target=top["field"],
                confidence=top["confidence"],
                method=top["method"],
                status="ambiguous" if ambiguous else "matched",
                candidates=candidates,
            )
        )

    # 同一字段被多列命中 → 冲突，只保留置信度最高的一列
    winners: Dict[str, int] = {}
    for index, item in enumerate(matches):
        if not item.target:
            continue
        current = winners.get(item.target)
        if current is None or item.confidence > matches[current].confidence:
            if current is not None:
                matches[current].target = None
                matches[current].status = "conflict"
            winners[item.target] = index
        else:
            item.target = None
            item.status = "conflict"

    return matches


def apply_overrides(matches: List[ColumnMatch], overrides: Dict[str, Optional[str]]) -> List[ColumnMatch]:
    """用户手动调整：显式指定 source → field，或置空表示忽略该列。

    手动指定的优先级高于自动匹配：若同一字段已被其他列占用，先解除占用，
    否则用户改了映射却仍写入旧列，属于静默错误。
    """
    by_source = {m.source: m for m in matches}
    for source, field in overrides.items():
        item = by_source.get(source)
        if item is None:
            continue
        if field:
            for other in matches:
                if other is not item and other.target == field:
                    other.target = None
                    other.status = "conflict"
            item.target = field
            item.method = "manual"
            item.confidence = 1.0
            item.status = "matched"
        else:
            item.target = None
            item.status = "unmatched"
    return matches


def required_missing(matches: List[ColumnMatch], target: str) -> List[str]:
    mapped = {m.target for m in matches if m.target}
    return [field for field in TARGETS[target]["required"] if field not in mapped]  # type: ignore[index]


def mapping_to_dict(matches: List[ColumnMatch]) -> Dict[str, str]:
    return {m.source: m.target for m in matches if m.target}


def matches_as_list(matches: List[ColumnMatch], target: str) -> List[Dict[str, Any]]:
    labels: Dict[str, str] = TARGETS[target]["labels"]  # type: ignore[assignment]
    return [
        {
            "source": m.source,
            "target": m.target,
            "target_label": labels.get(m.target, "") if m.target else "",
            "confidence": round(m.confidence, 2),
            "method": m.method,
            "status": m.status,
            "candidates": [
                {"field": c["field"], "label": labels.get(c["field"], c["field"]), "confidence": c["confidence"]}
                for c in m.candidates
            ],
        }
        for m in matches
    ]
