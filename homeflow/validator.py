from __future__ import annotations

from collections import defaultdict
from typing import Any

from .catalog import DOMAIN_SERVICES, SENSITIVE_SERVICES, service_parameters
from .models import (
    Action,
    AutomationIR,
    Condition,
    Device,
    DeviceInventory,
    Severity,
    Trigger,
    ValidationIssue,
)


def acknowledgement_key(action: Action) -> str:
    return f"confirm:{action.entity_id}:{action.service}"


def _issue(
    code: str,
    severity: Severity,
    path: str,
    message: str,
    *,
    requires_confirmation: bool = False,
    acknowledgement: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        path=path,
        message=message,
        requires_confirmation=requires_confirmation,
        acknowledgement_key=acknowledgement,
    )


def _validate_numeric_attribute(
    entity_id: str | None,
    attribute: str | None,
    path: str,
    inventory: dict[str, Device],
) -> list[ValidationIssue]:
    device = inventory.get(entity_id or "")
    if device is None or device.domain != "climate":
        return []
    if attribute != "current_temperature" or "current_temperature" not in device.capabilities:
        return [
            _issue(
                "UNSUPPORTED_ATTRIBUTE",
                Severity.BLOCKING,
                path + ".attribute",
                "本版空调数值规则只支持已声明的 current_temperature 室温；temperature 是目标设定温度",
            )
        ]
    return []


def _validate_trigger(trigger: Trigger, index: int, inventory: dict[str, Device]) -> list[ValidationIssue]:
    path = f"triggers[{index}]"
    issues: list[ValidationIssue] = []
    if trigger.trigger_type == "time" and not trigger.at:
        issues.append(_issue("MISSING_FIELD", Severity.BLOCKING, path + ".at", "时间触发器缺少 at"))
    elif trigger.trigger_type in {"state", "numeric_state"}:
        if not trigger.entity_id:
            issues.append(
                _issue("MISSING_FIELD", Severity.BLOCKING, path + ".entity_id", "设备触发器缺少 entity_id")
            )
        elif trigger.entity_id not in inventory:
            issues.append(
                _issue("UNKNOWN_ENTITY", Severity.BLOCKING, path + ".entity_id", f"设备不存在：{trigger.entity_id}")
            )
        if trigger.trigger_type == "state" and not trigger.to_state:
            issues.append(
                _issue("MISSING_FIELD", Severity.BLOCKING, path + ".to_state", "状态触发器缺少 to_state")
            )
        if trigger.trigger_type == "numeric_state" and trigger.above is None and trigger.below is None:
            issues.append(
                _issue("MISSING_FIELD", Severity.BLOCKING, path, "数值触发器至少需要 above 或 below")
            )
        if trigger.trigger_type == "numeric_state":
            issues.extend(_validate_numeric_attribute(trigger.entity_id, trigger.attribute, path, inventory))
    elif trigger.trigger_type == "sun" and trigger.event is None:
        issues.append(_issue("MISSING_FIELD", Severity.BLOCKING, path + ".event", "日出日落触发器缺少 event"))
    return issues


def _validate_condition(
    condition: Condition, index: int, inventory: dict[str, Device]
) -> list[ValidationIssue]:
    path = f"conditions[{index}]"
    issues: list[ValidationIssue] = []
    if condition.condition_type == "time":
        if not condition.after and not condition.before:
            issues.append(_issue("MISSING_FIELD", Severity.BLOCKING, path, "时间条件缺少 after 或 before"))
    else:
        if not condition.entity_id:
            issues.append(
                _issue("MISSING_FIELD", Severity.BLOCKING, path + ".entity_id", "设备条件缺少 entity_id")
            )
        elif condition.entity_id not in inventory:
            issues.append(
                _issue("UNKNOWN_ENTITY", Severity.BLOCKING, path + ".entity_id", f"设备不存在：{condition.entity_id}")
            )
        if condition.condition_type == "state" and condition.state is None:
            issues.append(_issue("MISSING_FIELD", Severity.BLOCKING, path + ".state", "状态条件缺少 state"))
        if condition.condition_type == "numeric_state" and condition.above is None and condition.below is None:
            issues.append(
                _issue("MISSING_FIELD", Severity.BLOCKING, path, "数值条件至少需要 above 或 below")
            )
        if condition.condition_type == "numeric_state":
            issues.extend(_validate_numeric_attribute(condition.entity_id, condition.attribute, path, inventory))
    return issues


def _effective_range(device: Device, parameter: str, global_range: tuple[float, float]) -> tuple[float, float]:
    if parameter not in device.parameter_ranges:
        return global_range
    device_min, device_max = device.parameter_ranges[parameter]
    return max(device_min, global_range[0]), min(device_max, global_range[1])


def _validate_action(
    action: Action,
    index: int,
    inventory: dict[str, Device],
    acknowledgements: set[str],
) -> list[ValidationIssue]:
    path = f"actions[{index}]"
    issues: list[ValidationIssue] = []
    device = inventory.get(action.entity_id)
    if device is None:
        return [_issue("UNKNOWN_ENTITY", Severity.BLOCKING, path + ".entity_id", f"设备不存在：{action.entity_id}")]

    service_domain = action.service.split(".", 1)[0] if "." in action.service else ""
    if service_domain != device.domain:
        issues.append(
            _issue(
                "DOMAIN_MISMATCH",
                Severity.BLOCKING,
                path + ".service",
                f"服务 {action.service} 不能用于 {device.domain} 设备",
            )
        )
        return issues

    allowed = set(device.allowed_services or DOMAIN_SERVICES.get(device.domain, {}))
    if action.service not in allowed:
        issues.append(
            _issue(
                "UNSUPPORTED_SERVICE",
                Severity.BLOCKING,
                path + ".service",
                f"{device.display_name} 不支持 {action.service}",
            )
        )
        return issues

    definitions = service_parameters(action.service)
    if definitions is None:
        issues.append(
            _issue("UNSUPPORTED_SERVICE", Severity.BLOCKING, path + ".service", f"服务未列入允许清单：{action.service}")
        )
        return issues

    unknown_parameters = set(action.parameters) - set(definitions)
    for parameter in sorted(unknown_parameters):
        issues.append(
            _issue(
                "UNKNOWN_PARAMETER",
                Severity.BLOCKING,
                path + f".parameters.{parameter}",
                f"{action.service} 不支持参数 {parameter}",
            )
        )

    for parameter, limit in definitions.items():
        if limit is None or parameter not in action.parameters:
            continue
        value: Any = action.parameters[parameter]
        if not isinstance(value, (int, float)):
            issues.append(
                _issue(
                    "INVALID_PARAMETER_TYPE",
                    Severity.BLOCKING,
                    path + f".parameters.{parameter}",
                    f"{parameter} 必须是数字",
                )
            )
            continue
        low, high = _effective_range(device, parameter, limit)
        if not low <= float(value) <= high:
            issues.append(
                _issue(
                    "PARAMETER_OUT_OF_RANGE",
                    Severity.BLOCKING,
                    path + f".parameters.{parameter}",
                    f"{parameter}={value} 超出允许范围 {low:g}–{high:g}",
                )
            )

    if action.service in SENSITIVE_SERVICES or device.sensitivity == "sensitive" and action.service.endswith("unlock"):
        key = acknowledgement_key(action)
        confirmed = key in acknowledgements
        issues.append(
            _issue(
                "SENSITIVE_ACTION",
                Severity.WARNING if confirmed else Severity.BLOCKING,
                path,
                "敏感动作已确认" if confirmed else "门锁解锁属于敏感动作，必须由用户明确确认",
                requires_confirmation=not confirmed,
                acknowledgement=key,
            )
        )
    return issues


def _conflict_issues(ir: AutomationIR) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_entity: dict[str, list[tuple[int, Action]]] = defaultdict(list)
    for index, action in enumerate(ir.actions):
        by_entity[action.entity_id].append((index, action))

    opposing = {
        frozenset({"light.turn_on", "light.turn_off"}),
        frozenset({"climate.turn_on", "climate.turn_off"}),
        frozenset({"cover.open_cover", "cover.close_cover"}),
        frozenset({"media_player.media_play", "media_player.media_pause"}),
        frozenset({"lock.lock", "lock.unlock"}),
    }
    for entity_id, items in by_entity.items():
        services = {item.service for _, item in items}
        if any(pair <= services for pair in opposing):
            issues.append(
                _issue(
                    "ACTION_CONFLICT",
                    Severity.BLOCKING,
                    "actions",
                    f"同一自动化对 {entity_id} 包含互相冲突的动作",
                )
            )

    triggered_entities = {
        trigger.entity_id
        for trigger in ir.triggers
        if trigger.trigger_type in {"state", "numeric_state"}
    }
    for index, action in enumerate(ir.actions):
        if action.entity_id in triggered_entities and action.service.endswith(".toggle"):
            issues.append(
                _issue(
                    "SELF_TRIGGER_LOOP",
                    Severity.BLOCKING,
                    f"actions[{index}]",
                    f"{action.entity_id} 同时作为触发设备并执行 toggle，存在重复触发风险",
                )
            )
    return issues


def validate_automation(ir: AutomationIR, inventory: DeviceInventory) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    device_map = inventory.by_id()
    if ir.clarification_questions:
        issues.append(
            _issue(
                "CLARIFICATION_REQUIRED",
                Severity.BLOCKING,
                "clarification_questions",
                "需求信息不足，请先回答澄清问题",
            )
        )
    for index, trigger in enumerate(ir.triggers):
        issues.extend(_validate_trigger(trigger, index, device_map))
    for index, condition in enumerate(ir.conditions):
        issues.extend(_validate_condition(condition, index, device_map))
    acknowledgements = set(ir.risk_acknowledgements)
    for index, action in enumerate(ir.actions):
        issues.extend(_validate_action(action, index, device_map, acknowledgements))
    issues.extend(_conflict_issues(ir))
    return issues


def has_blocking_issues(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == Severity.BLOCKING for issue in issues)
