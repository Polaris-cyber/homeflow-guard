import json
from pathlib import Path

import pytest

from homeflow.exporter import ExportBlocked, export_yaml, static_yaml_check, yaml_to_ir
from homeflow.io_utils import InputError, parse_inventory_bytes
from homeflow.models import AutomationIR, SimulationInput
from homeflow.simulator import simulate
from homeflow.validator import acknowledgement_key, validate_automation


ROOT = Path(__file__).resolve().parents[1]


def valid_ir() -> AutomationIR:
    return AutomationIR.model_validate(
        {
            "name": "回家开启客厅舒适模式",
            "description": "玄关检测到有人且窗户关闭时，开灯并将空调设为 22℃。",
            "triggers": [
                {
                    "trigger_type": "state",
                    "entity_id": "binary_sensor.hall_motion",
                    "to_state": "on",
                }
            ],
            "conditions": [
                {
                    "condition_type": "state",
                    "entity_id": "binary_sensor.living_window",
                    "state": "off",
                }
            ],
            "actions": [
                {"entity_id": "light.living_main", "service": "light.turn_on", "parameters": {"brightness": 180}},
                {
                    "entity_id": "climate.living_ac",
                    "service": "climate.set_temperature",
                    "parameters": {"temperature": 22},
                },
            ],
            "clarification_questions": [],
            "risk_acknowledgements": [],
        }
    )


def test_inventory_rejects_sensitive_keys():
    payload = b'{"inventory_id":"x","title":"x","access_token":"secret","devices":[]}'
    with pytest.raises(InputError, match="禁止字段"):
        parse_inventory_bytes(payload, "inventory.json")


def test_valid_automation_exports_current_ha_shape(inventory):
    ir = valid_ir()
    assert not validate_automation(ir, inventory)
    content = export_yaml(ir, inventory)
    valid, errors = static_yaml_check(content)
    assert valid, errors
    assert "triggers:" in content
    assert "actions:" in content
    assert "climate.set_temperature" in content


def test_yaml_snapshot(inventory):
    expected = (ROOT / "tests" / "snapshots" / "valid_automation.yaml").read_text(encoding="utf-8")
    assert export_yaml(valid_ir(), inventory).replace("\r\n", "\n") == expected.replace("\r\n", "\n")


def test_supported_yaml_round_trip(inventory):
    source = valid_ir()
    parsed = yaml_to_ir(export_yaml(source, inventory))
    assert parsed.model_dump(mode="json") == source.model_dump(mode="json")


def test_unknown_entity_fails_closed(inventory):
    payload = valid_ir().model_dump()
    payload["actions"][0]["entity_id"] = "light.invented"
    ir = AutomationIR.model_validate(payload)
    issues = validate_automation(ir, inventory)
    assert any(issue.code == "UNKNOWN_ENTITY" and issue.severity.value == "blocking" for issue in issues)
    with pytest.raises(ExportBlocked):
        export_yaml(ir, inventory)


def test_parameter_range_fails_closed(inventory):
    payload = valid_ir().model_dump()
    payload["actions"][1]["parameters"]["temperature"] = 35
    ir = AutomationIR.model_validate(payload)
    issues = validate_automation(ir, inventory)
    assert any(issue.code == "PARAMETER_OUT_OF_RANGE" for issue in issues)


def test_unsupported_service_and_unknown_parameter_fail_closed(inventory):
    payload = valid_ir().model_dump()
    payload["actions"] = [
        {"entity_id": "light.living_main", "service": "light.flash_forever", "parameters": {}},
        {"entity_id": "climate.living_ac", "service": "climate.set_temperature", "parameters": {"mystery": 1}},
    ]
    issues = validate_automation(AutomationIR.model_validate(payload), inventory)
    codes = {issue.code for issue in issues}
    assert {"UNSUPPORTED_SERVICE", "UNKNOWN_PARAMETER"} <= codes


def test_conflicting_actions_are_blocked(inventory):
    payload = valid_ir().model_dump()
    payload["actions"].append(
        {"entity_id": "light.living_main", "service": "light.turn_off", "parameters": {}}
    )
    issues = validate_automation(AutomationIR.model_validate(payload), inventory)
    assert any(issue.code == "ACTION_CONFLICT" for issue in issues)


def test_self_trigger_toggle_loop_is_blocked(inventory):
    payload = valid_ir().model_dump()
    payload["triggers"] = [
        {"trigger_type": "state", "entity_id": "light.living_main", "to_state": "on"}
    ]
    payload["actions"] = [
        {"entity_id": "light.living_main", "service": "light.toggle", "parameters": {}}
    ]
    issues = validate_automation(AutomationIR.model_validate(payload), inventory)
    assert any(issue.code == "SELF_TRIGGER_LOOP" for issue in issues)


def test_lock_unlock_requires_exact_confirmation(inventory):
    payload = valid_ir().model_dump()
    payload["actions"] = [{"entity_id": "lock.front_door", "service": "lock.unlock", "parameters": {}}]
    ir = AutomationIR.model_validate(payload)
    issues = validate_automation(ir, inventory)
    sensitive = next(issue for issue in issues if issue.code == "SENSITIVE_ACTION")
    assert sensitive.severity.value == "blocking"
    payload["risk_acknowledgements"] = [acknowledgement_key(ir.actions[0])]
    confirmed = validate_automation(AutomationIR.model_validate(payload), inventory)
    assert next(issue for issue in confirmed if issue.code == "SENSITIVE_ACTION").severity.value == "warning"


def test_simulation_executes_and_changes_state(inventory):
    states = json.loads((ROOT / "data" / "sample_states.json").read_text(encoding="utf-8"))
    result = simulate(valid_ir(), inventory, SimulationInput.model_validate({"states": states}))
    assert result.status == "executed"
    assert result.final_states["light.living_main"].state == "on"
    assert result.final_states["climate.living_ac"].attributes["temperature"] == 22


def test_room_temperature_trigger_keeps_measured_and_target_temperatures_distinct(inventory):
    payload = valid_ir().model_dump()
    payload["triggers"] = [
        {
            "trigger_type": "numeric_state",
            "entity_id": "climate.living_ac",
            "attribute": "current_temperature",
            "below": 18,
        }
    ]
    ir = AutomationIR.model_validate(payload)
    states = json.loads((ROOT / "data" / "sample_states.json").read_text(encoding="utf-8"))
    assert states["climate.living_ac"]["attributes"]["current_temperature"] == 17
    assert states["climate.living_ac"]["attributes"]["temperature"] == 22
    assert not validate_automation(ir, inventory)
    assert "attribute: current_temperature" in export_yaml(ir, inventory)

    result = simulate(ir, inventory, SimulationInput.model_validate({"states": states}))
    assert result.status == "executed"
    assert result.final_states["climate.living_ac"].attributes["temperature"] == 22
    assert result.final_states["climate.living_ac"].attributes["current_temperature"] == 17


@pytest.mark.parametrize("field", ["triggers", "conditions"])
def test_target_temperature_cannot_masquerade_as_room_temperature(inventory, field):
    payload = valid_ir().model_dump()
    if field == "triggers":
        payload[field] = [
            {"trigger_type": "numeric_state", "entity_id": "climate.living_ac", "attribute": "temperature", "below": 18}
        ]
    else:
        payload[field] = [
            {"condition_type": "numeric_state", "entity_id": "climate.living_ac", "attribute": "temperature", "below": 18}
        ]
    ir = AutomationIR.model_validate(payload)
    issues = validate_automation(ir, inventory)
    assert any(issue.code == "UNSUPPORTED_ATTRIBUTE" and issue.severity.value == "blocking" for issue in issues)
    with pytest.raises(ExportBlocked):
        export_yaml(ir, inventory)


def test_simulation_records_condition_block(inventory):
    states = json.loads((ROOT / "data" / "sample_states.json").read_text(encoding="utf-8"))
    states["binary_sensor.living_window"]["state"] = "on"
    result = simulate(valid_ir(), inventory, SimulationInput.model_validate({"states": states}))
    assert result.status == "conditions_failed"
    assert result.final_states["light.living_main"].state == states["light.living_main"]["state"]


def test_clarification_prevents_export(inventory):
    ir = AutomationIR.model_validate(
        {
            "name": "信息不足",
            "triggers": [],
            "conditions": [],
            "actions": [],
            "clarification_questions": ["要控制哪个房间的灯？"],
            "risk_acknowledgements": [],
        }
    )
    issues = validate_automation(ir, inventory)
    assert any(issue.code == "CLARIFICATION_REQUIRED" for issue in issues)
