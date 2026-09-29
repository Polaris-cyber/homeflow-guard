from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import yaml

from .models import AutomationIR, Condition, DeviceInventory, Trigger, ValidationIssue
from .validator import has_blocking_issues, validate_automation


class ExportBlocked(ValueError):
    pass


def _clean(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None and value != {}}


def _trigger_to_ha(trigger: Trigger) -> dict[str, Any] | None:
    if trigger.trigger_type == "manual":
        return None
    if trigger.trigger_type == "time":
        return {"trigger": "time", "at": trigger.at}
    if trigger.trigger_type == "state":
        return _clean(
            {
                "trigger": "state",
                "entity_id": trigger.entity_id,
                "from": trigger.from_state,
                "to": trigger.to_state,
            }
        )
    if trigger.trigger_type == "numeric_state":
        return _clean(
            {
                "trigger": "numeric_state",
                "entity_id": trigger.entity_id,
                "attribute": trigger.attribute,
                "above": trigger.above,
                "below": trigger.below,
            }
        )
    return _clean({"trigger": "sun", "event": trigger.event, "offset": trigger.offset})


def _condition_to_ha(condition: Condition) -> dict[str, Any]:
    if condition.condition_type == "time":
        return _clean({"condition": "time", "after": condition.after, "before": condition.before})
    if condition.condition_type == "state":
        return {"condition": "state", "entity_id": condition.entity_id, "state": condition.state}
    return _clean(
        {
            "condition": "numeric_state",
            "entity_id": condition.entity_id,
            "attribute": condition.attribute,
            "above": condition.above,
            "below": condition.below,
        }
    )


def automation_to_dict(ir: AutomationIR) -> dict[str, Any]:
    triggers = [item for trigger in ir.triggers if (item := _trigger_to_ha(trigger)) is not None]
    return {
        "alias": ir.name,
        "description": ir.description,
        "triggers": triggers,
        "conditions": [_condition_to_ha(condition) for condition in ir.conditions],
        "actions": [
            _clean(
                {
                    "action": action.service,
                    "target": {"entity_id": action.entity_id},
                    "data": action.parameters,
                }
            )
            for action in ir.actions
        ],
        "mode": "single",
    }


def export_yaml(ir: AutomationIR, inventory: DeviceInventory) -> str:
    issues = validate_automation(ir, inventory)
    if has_blocking_issues(issues):
        raise ExportBlocked("存在阻断问题，不能导出 YAML")
    return yaml.safe_dump(
        automation_to_dict(ir),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def static_yaml_check(content: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        return False, [f"YAML 解析失败：{exc}"]
    if not isinstance(parsed, dict):
        return False, ["YAML 顶层必须是对象"]
    required = {"alias", "triggers", "conditions", "actions", "mode"}
    missing = required - set(parsed)
    if missing:
        errors.append("缺少字段：" + ", ".join(sorted(missing)))
    if parsed.get("mode") != "single":
        errors.append("v1 仅支持 mode: single")
    if not isinstance(parsed.get("triggers"), list):
        errors.append("triggers 必须是数组")
    if not isinstance(parsed.get("conditions"), list):
        errors.append("conditions 必须是数组")
    if not isinstance(parsed.get("actions"), list) or not parsed.get("actions"):
        errors.append("actions 必须是非空数组")
    return not errors, errors


def validation_report_json(issues: list[ValidationIssue]) -> str:
    return json.dumps([issue.model_dump(mode="json") for issue in issues], ensure_ascii=False, indent=2)


def build_export_bundle(yaml_content: str, report_content: str) -> bytes:
    """Package the reviewable YAML and validation evidence into one download."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("homeflow-automation.yaml", yaml_content)
        archive.writestr("homeflow-validation.json", report_content)
    return buffer.getvalue()


def yaml_to_ir(content: str) -> AutomationIR:
    """Convert the supported Home Assistant YAML subset back to AutomationIR.

    This parser exists for baseline evaluation. It intentionally rejects advanced
    Home Assistant syntax that is outside the v1 product boundary.
    """
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 解析失败：{exc}") from exc
    if isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise ValueError("YAML 顶层必须是对象")

    raw_triggers = parsed.get("triggers", parsed.get("trigger", []))
    raw_conditions = parsed.get("conditions", parsed.get("condition", []))
    raw_actions = parsed.get("actions", parsed.get("action", []))
    if isinstance(raw_triggers, dict):
        raw_triggers = [raw_triggers]
    if isinstance(raw_conditions, dict):
        raw_conditions = [raw_conditions]
    if isinstance(raw_actions, dict):
        raw_actions = [raw_actions]

    triggers: list[dict[str, Any]] = []
    for item in raw_triggers or []:
        kind = item.get("trigger", item.get("platform"))
        if kind == "time":
            triggers.append({"trigger_type": "time", "at": str(item.get("at", ""))})
        elif kind == "state":
            triggers.append(
                {
                    "trigger_type": "state",
                    "entity_id": item.get("entity_id"),
                    "from_state": item.get("from"),
                    "to_state": item.get("to"),
                }
            )
        elif kind == "numeric_state":
            triggers.append(
                {
                    "trigger_type": "numeric_state",
                    "entity_id": item.get("entity_id"),
                    "attribute": item.get("attribute"),
                    "above": item.get("above"),
                    "below": item.get("below"),
                }
            )
        elif kind == "sun":
            triggers.append(
                {"trigger_type": "sun", "event": item.get("event"), "offset": item.get("offset")}
            )
        else:
            raise ValueError(f"不支持的 trigger：{kind}")

    conditions: list[dict[str, Any]] = []
    for item in raw_conditions or []:
        kind = item.get("condition")
        if kind == "time":
            conditions.append(
                {"condition_type": "time", "after": item.get("after"), "before": item.get("before")}
            )
        elif kind == "state":
            conditions.append(
                {"condition_type": "state", "entity_id": item.get("entity_id"), "state": item.get("state")}
            )
        elif kind == "numeric_state":
            conditions.append(
                {
                    "condition_type": "numeric_state",
                    "entity_id": item.get("entity_id"),
                    "attribute": item.get("attribute"),
                    "above": item.get("above"),
                    "below": item.get("below"),
                }
            )
        else:
            raise ValueError(f"不支持的 condition：{kind}")

    actions: list[dict[str, Any]] = []
    for item in raw_actions or []:
        service = item.get("action", item.get("service"))
        target = item.get("target", {})
        entity_id = target.get("entity_id", item.get("entity_id"))
        if isinstance(entity_id, list):
            if len(entity_id) != 1:
                raise ValueError("v1 每个动作只支持一个 entity_id")
            entity_id = entity_id[0]
        actions.append({"entity_id": entity_id, "service": service, "parameters": item.get("data", {})})

    return AutomationIR.model_validate(
        {
            "name": str(parsed.get("alias") or "基线生成规则"),
            "description": str(parsed.get("description") or ""),
            "triggers": triggers,
            "conditions": conditions,
            "actions": actions,
            "clarification_questions": [],
            "risk_acknowledgements": [],
        }
    )
