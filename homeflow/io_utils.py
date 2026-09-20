from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import AutomationIR, DeviceInventory


MAX_UPLOAD_BYTES = 1_000_000
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(access[_-]?token|api[_-]?key|password|secret|home[_-]?address|latitude|longitude)"
)


class InputError(ValueError):
    pass


def _decode_payload(payload: bytes) -> str:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise InputError("文件超过 1MB 限制")
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("文件必须使用 UTF-8 编码") from exc


def _parse_text(text: str, filename: str) -> Any:
    try:
        if filename.lower().endswith(".json"):
            return json.loads(text)
        return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise InputError(f"无法解析 {filename}：{exc}") from exc


def find_sensitive_keys(value: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if SENSITIVE_KEY_PATTERN.search(str(key)):
                findings.append(path)
            findings.extend(find_sensitive_keys(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(find_sensitive_keys(item, f"{prefix}[{index}]"))
    return findings


def parse_inventory_bytes(payload: bytes, filename: str) -> DeviceInventory:
    raw = _parse_text(_decode_payload(payload), filename)
    sensitive = find_sensitive_keys(raw)
    if sensitive:
        raise InputError("设备清单包含禁止字段：" + ", ".join(sensitive[:5]))
    try:
        return DeviceInventory.model_validate(raw)
    except ValidationError as exc:
        raise InputError(str(exc)) from exc


def load_inventory(path: str | Path) -> DeviceInventory:
    source = Path(path)
    return parse_inventory_bytes(source.read_bytes(), source.name)


def parse_ir_text(text: str) -> AutomationIR:
    try:
        return AutomationIR.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InputError(f"自动化规则 JSON 无效：{exc}") from exc
