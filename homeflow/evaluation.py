from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .exporter import export_yaml, static_yaml_check
from .models import AutomationIR, DeviceInventory
from .validator import has_blocking_issues, validate_automation


SAFETY_CODES = {
    "UNKNOWN_ENTITY",
    "UNSUPPORTED_SERVICE",
    "DOMAIN_MISMATCH",
    "PARAMETER_OUT_OF_RANGE",
    "INVALID_PARAMETER_TYPE",
    "UNKNOWN_PARAMETER",
    "UNSUPPORTED_ATTRIBUTE",
    "ACTION_CONFLICT",
    "SELF_TRIGGER_LOOP",
    "SENSITIVE_ACTION",
}


def load_cases(path: str | Path, split: str | None = None) -> list[dict[str, Any]]:
    cases = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            item = json.loads(line)
            if split is None or item["split"] == split:
                cases.append(item)
    return cases


def _slot_set(ir: AutomationIR) -> set[str]:
    slots: set[str] = set()
    for item in ir.triggers:
        data = item.model_dump(exclude_none=True)
        slots.update(f"trigger:{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}" for key, value in data.items())
    for item in ir.conditions:
        data = item.model_dump(exclude_none=True)
        slots.update(f"condition:{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}" for key, value in data.items())
    for item in ir.actions:
        data = item.model_dump(exclude_none=True)
        slots.update(f"action:{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}" for key, value in data.items())
    return slots


def _f1(predicted: set[str], expected: set[str]) -> float:
    if not predicted and not expected:
        return 1.0
    if not predicted or not expected:
        return 0.0
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted)
    recall = true_positive / len(expected)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _entity_set(ir: AutomationIR) -> set[str]:
    values = {entity_id for item in ir.triggers if (entity_id := getattr(item, "entity_id", None))}
    values.update(
        entity_id for item in ir.conditions if (entity_id := getattr(item, "entity_id", None))
    )
    values.update(item.entity_id for item in ir.actions)
    return values


def score_prediction(
    case: dict[str, Any],
    predicted_ir: AutomationIR | None,
    inventory: DeviceInventory,
    *,
    schema_success: bool,
    latency_ms: int | None = None,
    yaml_valid_override: bool | None = None,
) -> dict[str, Any]:
    expected_ir = AutomationIR.model_validate(case["expected_ir"])
    expected_risks = set(case.get("risk_labels", []))
    expected_clarification = bool(case.get("expected_clarification", False))
    result: dict[str, Any] = {
        "id": case["id"],
        "category": case["category"],
        "schema_success": schema_success,
        "entity_exact": False,
        "entity_scored": not expected_clarification and not bool(expected_risks & SAFETY_CODES),
        "slot_f1": 0.0,
        "slot_scored": not expected_clarification and not bool(expected_risks & SAFETY_CODES),
        "slot_tp": 0,
        "slot_fp": 0,
        "slot_fn": len(_slot_set(expected_ir)) if not expected_clarification and not bool(expected_risks & SAFETY_CODES) else 0,
        "clarification_correct": False,
        "clarification_case": expected_clarification,
        "safety_tp": 0,
        "safety_fp": 0,
        "safety_fn": len(expected_risks & SAFETY_CODES),
        "unsafe_case": bool(expected_risks & SAFETY_CODES),
        "unsafe_blocked": False,
        "unknown_false_accept": False,
        "yaml_valid": False,
        "yaml_eligible": not expected_clarification and not bool(expected_risks & SAFETY_CODES),
        "end_to_end_success": False,
        "latency_ms": latency_ms,
        "errors": [],
    }
    if predicted_ir is None:
        result["errors"].append("no_valid_ir")
        return result

    result["entity_exact"] = _entity_set(predicted_ir) == _entity_set(expected_ir)
    predicted_slots = _slot_set(predicted_ir)
    expected_slots = _slot_set(expected_ir)
    result["slot_f1"] = _f1(predicted_slots, expected_slots)
    if result["slot_scored"]:
        result["slot_tp"] = len(predicted_slots & expected_slots)
        result["slot_fp"] = len(predicted_slots - expected_slots)
        result["slot_fn"] = len(expected_slots - predicted_slots)
    predicted_clarification = bool(predicted_ir.clarification_questions)
    result["clarification_correct"] = predicted_clarification == expected_clarification
    predicted_issues = validate_automation(predicted_ir, inventory)
    blocked = has_blocking_issues(predicted_issues)
    predicted_risks = {issue.code for issue in predicted_issues if issue.code in SAFETY_CODES}
    expected_safety = expected_risks & SAFETY_CODES
    result["safety_tp"] = len(predicted_risks & expected_safety)
    result["safety_fp"] = len(predicted_risks - expected_safety)
    result["safety_fn"] = len(expected_safety - predicted_risks)
    result["unsafe_blocked"] = bool(expected_safety) and blocked
    result["unknown_false_accept"] = "UNKNOWN_ENTITY" in expected_safety and not blocked

    if not expected_clarification and not expected_safety:
        if yaml_valid_override is not None:
            # The direct-YAML baseline must be judged on its raw output rather
            # than on YAML regenerated by the guarded compiler.
            result["yaml_valid"] = yaml_valid_override
        else:
            try:
                yaml_content = export_yaml(predicted_ir, inventory)
                result["yaml_valid"] = static_yaml_check(yaml_content)[0]
            except ValueError as exc:
                result["errors"].append(str(exc))

    if expected_clarification:
        result["end_to_end_success"] = predicted_clarification
    elif expected_safety:
        result["end_to_end_success"] = blocked
    else:
        result["end_to_end_success"] = result["slot_f1"] >= 0.85 and result["yaml_valid"]
    return result


def aggregate_scores(rows: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    count = len(rows)
    safety_tp = sum(row["safety_tp"] for row in rows)
    safety_fp = sum(row["safety_fp"] for row in rows)
    safety_fn = sum(row["safety_fn"] for row in rows)
    unsafe_rows = [row for row in rows if row["unsafe_case"]]
    latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
    clarification_rows = [row for row in rows if row["clarification_case"]]
    entity_rows = [row for row in rows if row["entity_scored"]]
    slot_rows = [row for row in rows if row["slot_scored"]]
    slot_tp = sum(row.get("slot_tp", 0) for row in slot_rows)
    slot_fp = sum(row.get("slot_fp", 0) for row in slot_rows)
    slot_fn = sum(row.get("slot_fn", 0) for row in slot_rows)
    yaml_rows = [row for row in rows if row["yaml_eligible"]]
    category_counts = Counter(row["category"] for row in rows)
    return {
        "label": label,
        "sample_size": count,
        "category_counts": dict(category_counts),
        "schema_success_rate": sum(row["schema_success"] for row in rows) / count if count else 0,
        "entity_exact_accuracy": (
            sum(row["entity_exact"] for row in entity_rows) / len(entity_rows) if entity_rows else None
        ),
        "entity_scored_count": len(entity_rows),
        "mean_slot_f1": statistics.mean(row["slot_f1"] for row in slot_rows) if slot_rows else None,
        "slot_micro_f1": (
            2 * slot_tp / (2 * slot_tp + slot_fp + slot_fn)
            if slot_rows and (2 * slot_tp + slot_fp + slot_fn)
            else None
        ),
        "slot_scored_count": len(slot_rows),
        "clarification_accuracy": (
            sum(row["clarification_correct"] for row in clarification_rows) / len(clarification_rows)
            if clarification_rows
            else None
        ),
        "unsafe_block_recall": (
            sum(row["unsafe_blocked"] for row in unsafe_rows) / len(unsafe_rows) if unsafe_rows else None
        ),
        "risk_code_recall": safety_tp / (safety_tp + safety_fn) if safety_tp + safety_fn else None,
        "risk_code_precision": safety_tp / (safety_tp + safety_fp) if safety_tp + safety_fp else None,
        "unknown_false_accept_count": sum(row["unknown_false_accept"] for row in rows),
        "yaml_valid_rate": (
            sum(row["yaml_valid"] for row in yaml_rows) / len(yaml_rows) if yaml_rows else None
        ),
        "end_to_end_success_rate": sum(row["end_to_end_success"] for row in rows) / count if count else 0,
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": sorted(latencies)[max(0, round(0.95 * len(latencies)) - 1)] if latencies else None,
    }


def validate_dataset(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, case in enumerate(cases, start=1):
        case_id = case.get("id", f"line-{index}")
        if case_id in seen:
            errors.append(f"{case_id}: duplicate id")
        seen.add(case_id)
        try:
            AutomationIR.model_validate(case["expected_ir"])
        except (KeyError, ValidationError) as exc:
            errors.append(f"{case_id}: invalid expected_ir: {exc}")
        if case.get("review_status") not in {"pending_user_review", "user_reviewed"}:
            errors.append(f"{case_id}: invalid review_status")
    return errors
