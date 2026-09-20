"""Conservative evidence checks between a request and model-proposed actions.

These checks intentionally cover only explicit numeric parameters and light
scope. They are a post-test safety patch, not a general semantic verifier.
"""

from __future__ import annotations

import re
import unicodedata

from .models import AutomationIR, DeviceInventory, Severity, ValidationIssue


def grounding_issues(
    ir: AutomationIR, user_request: str, inventory: DeviceInventory
) -> list[ValidationIssue]:
    if ir.clarification_questions:
        return []
    request = unicodedata.normalize("NFKC", user_request)
    numbers = {float(value) for value in re.findall(r"\d+(?:\.\d+)?", request)}
    by_id = inventory.by_id()
    multiple_lights = sum(device.domain == "light" for device in inventory.devices) > 1
    all_lights = any(word in request for word in ("所有灯", "全部灯", "每盏灯"))
    issues: list[ValidationIssue] = []

    for index, action in enumerate(ir.actions):
        device = by_id.get(action.entity_id)
        if device is None:
            continue  # The inventory validator handles unknown entities.
        if device.domain == "light" and multiple_lights and not all_lights:
            named = any(
                token and token in request
                for token in (device.area, device.display_name, device.entity_id)
            )
            if not named:
                issues.append(
                    ValidationIssue(
                        code="AMBIGUOUS_DEVICE_SCOPE",
                        severity=Severity.BLOCKING,
                        path=f"actions[{index}].entity_id",
                        message="需求未明确要控制哪盏灯，请补充房间或设备名称。",
                    )
                )
        for parameter, value in action.parameters.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if float(value) not in numbers:
                issues.append(
                    ValidationIssue(
                        code="UNGROUNDED_PARAMETER",
                        severity=Severity.BLOCKING,
                        path=f"actions[{index}].parameters.{parameter}",
                        message=f"需求中没有明确数值 {value:g}，请确认 {parameter} 的目标值。",
                    )
                )
    return issues
