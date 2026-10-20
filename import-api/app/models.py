"""导入问题的内部模型。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class Issue:
    row_number: int
    issue_code: str
    issue_message: str
    field_name: Optional[str] = None
    severity: str = "error"

    def as_tuple(self) -> tuple:
        return (
            self.row_number,
            self.field_name,
            self.issue_code,
            self.severity,
            self.issue_message[:500],
        )
