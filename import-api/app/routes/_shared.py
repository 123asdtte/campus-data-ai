"""路由共享小工具：避免 routes 反向 import main 造成循环依赖。"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Dict, Optional

from fastapi import HTTPException

from .. import service


def handle(exc: service.ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def parse_mapping(raw: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """解析前端传来的列映射；非法 JSON 直接报 400，不静默忽略。"""
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"mapping 不是合法 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="mapping 必须是 {原始列名: 字段名} 对象")
    return {str(key): (str(val) if val else None) for key, val in value.items()}


def decode_base64(raw: str) -> bytes:
    """兼容两种输出：纯 base64，或带 data URL 前缀的 base64。"""
    text = raw.strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    text = "".join(text.split())
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return base64.b64decode(text, validate=False)
