from __future__ import annotations

from copy import deepcopy
from datetime import time
from typing import Any

from .catalog import infer_action_state
from .models import (
    AutomationIR,
    Condition,
    DeviceInventory,
    EntityState,
    SimulationInput,
    SimulationResult,
    TraceStep,
    Trigger,
)
from .validator import has_blocking_issues, validate_automation


def _parse_time(value: str) -> time:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        parts.append(0)
    return time(*parts)


def _numeric_value(state: EntityState | None, attribute: str | None) -> float | None:
    if state is None:
        return None
    raw: Any = state.attributes.get(attribute) if attribute else state.state
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _threshold_matches(value: float | None, above: float | None, below: float | None) -> bool:
    if value is None:
        return False
    return (above is None or value > above) and (below is None or value < below)


def _trigger_matches(trigger: Trigger, context: SimulationInput) -> tuple[bool, str]:
    if trigger.trigger_type == "manual":
        return context.manual, "手动触发已启用" if context.manual else "未启用手动触发"
    if trigger.trigger_type == "time":
        matched = _parse_time(context.now_time) == _parse_time(trigger.at or "00:00:00")
        return matched, f"当前时间 {context.now_time} {'匹配' if matched else '不匹配'} {trigger.at}"
    if trigger.trigger_type == "sun":
        matched = context.sun_event == trigger.event
        return matched, f"太阳事件 {context.sun_event or '无'} {'匹配' if matched else '不匹配'} {trigger.event}"
    state = context.states.get(trigger.entity_id or "")
    if trigger.trigger_type == "state":
        matched = state is not None and state.state == trigger.to_state
        actual = state.state if state else "缺失"
        return matched, f"{trigger.entity_id} 当前为 {actual}，目标为 {trigger.to_state}"
    value = _numeric_value(state, trigger.attribute)
    matched = _threshold_matches(value, trigger.above, trigger.below)
    return matched, f"{trigger.entity_id} 数值 {value}，阈值 above={trigger.above}, below={trigger.below}"


def _condition_matches(condition: Condition, context: SimulationInput) -> tuple[bool, str]:
    if condition.condition_type == "time":
        now = _parse_time(context.now_time)
        after_ok = condition.after is None or now >= _parse_time(condition.after)
        before_ok = condition.before is None or now <= _parse_time(condition.before)
        return after_ok and before_ok, f"当前时间 {context.now_time}，允许范围 {condition.after or '*'}–{condition.before or '*'}"
    state = context.states.get(condition.entity_id or "")
    if condition.condition_type == "state":
        matched = state is not None and state.state == condition.state
        actual = state.state if state else "缺失"
        return matched, f"{condition.entity_id} 当前为 {actual}，要求为 {condition.state}"
    value = _numeric_value(state, condition.attribute)
    matched = _threshold_matches(value, condition.above, condition.below)
    return matched, f"{condition.entity_id} 数值 {value}，阈值 above={condition.above}, below={condition.below}"


def simulate(
    ir: AutomationIR,
    inventory: DeviceInventory,
    context: SimulationInput,
) -> SimulationResult:
    trace: list[TraceStep] = []
    issues = validate_automation(ir, inventory)
    if has_blocking_issues(issues):
        trace.append(
            TraceStep(
                step=1,
                stage="validation",
                status="blocked",
                message="；".join(issue.message for issue in issues if issue.severity.value == "blocking"),
            )
        )
        return SimulationResult(
            status="blocked",
            initial_states=context.states,
            final_states=context.states,
            trace=trace,
        )

    trace.append(TraceStep(step=1, stage="validation", status="passed", message="规则校验通过"))
    step = 2
    trigger_results = []
    for trigger in ir.triggers:
        matched, message = _trigger_matches(trigger, context)
        trigger_results.append(matched)
        trace.append(
            TraceStep(step=step, stage="trigger", status="passed" if matched else "failed", message=message)
        )
        step += 1
    if ir.triggers and not any(trigger_results):
        return SimulationResult(
            status="not_triggered",
            initial_states=context.states,
            final_states=context.states,
            trace=trace,
        )

    for condition in ir.conditions:
        matched, message = _condition_matches(condition, context)
        trace.append(
            TraceStep(step=step, stage="condition", status="passed" if matched else "failed", message=message)
        )
        step += 1
        if not matched:
            return SimulationResult(
                status="conditions_failed",
                initial_states=context.states,
                final_states=context.states,
                trace=trace,
            )

    states = deepcopy(context.states)
    for action in ir.actions:
        before_state = states.get(action.entity_id, EntityState(state="unknown"))
        after_state = deepcopy(before_state)
        after_state.state = infer_action_state(action.service, action.parameters, before_state.state)
        if action.service == "climate.set_temperature":
            after_state.attributes["temperature"] = action.parameters["temperature"]
        elif action.service == "light.turn_on" and "brightness" in action.parameters:
            after_state.attributes["brightness"] = action.parameters["brightness"]
        elif action.service == "cover.set_cover_position":
            after_state.attributes["position"] = action.parameters["position"]
            after_state.state = "open" if action.parameters["position"] > 0 else "closed"
        elif action.service == "media_player.volume_set":
            after_state.attributes["volume_level"] = action.parameters["volume_level"]
        elif action.service == "media_player.play_media":
            after_state.state = "playing"
            after_state.attributes.update(action.parameters)
        states[action.entity_id] = after_state
        trace.append(
            TraceStep(
                step=step,
                stage="action",
                status="passed",
                message=f"执行 {action.service} → {action.entity_id}",
                before=before_state.model_dump(),
                after=after_state.model_dump(),
            )
        )
        step += 1

    trace.append(TraceStep(step=step, stage="result", status="passed", message="自动化执行完成"))
    return SimulationResult(
        status="executed",
        initial_states=context.states,
        final_states=states,
        trace=trace,
    )
