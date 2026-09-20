import json
from pathlib import Path

from homeflow.compiler import compile_request
from homeflow.grounding import grounding_issues
from homeflow.models import AutomationIR
from homeflow.validator import has_blocking_issues, validate_automation


ROOT = Path(__file__).resolve().parents[1]


def _case(case_id):
    for line in (ROOT / "data" / "gold_cases.jsonl").read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        if case["id"] == case_id:
            return case
    raise AssertionError(case_id)


def test_explicit_brightness_and_room_are_grounded(inventory):
    case = _case("S01")
    ir = AutomationIR.model_validate(case["expected_ir"])
    assert not grounding_issues(ir, case["user_request"], inventory)


def test_ambiguous_light_and_invented_brightness_are_blocked(inventory):
    proposal = AutomationIR.model_validate(
        {
            "name": "有人时调暗所有灯",
            "triggers": [
                {
                    "trigger_type": "state",
                    "entity_id": "binary_sensor.hall_motion",
                    "to_state": "on",
                }
            ],
            "conditions": [],
            "actions": [
                {
                    "entity_id": "light.living_main",
                    "service": "light.turn_on",
                    "parameters": {"brightness": 100},
                }
            ],
            "clarification_questions": [],
            "risk_acknowledgements": [],
        }
    )
    issues = grounding_issues(proposal, "有人时把灯调暗。", inventory)
    assert {issue.code for issue in issues} == {"AMBIGUOUS_DEVICE_SCOPE", "UNGROUNDED_PARAMETER"}
    assert has_blocking_issues(issues)


def test_compiler_discards_ungrounded_model_rule(inventory):
    case = _case("A05")
    proposal = {
        "name": "有人时调暗所有灯",
        "triggers": [
            {"trigger_type": "state", "entity_id": "binary_sensor.hall_motion", "to_state": "on"}
        ],
        "conditions": [],
        "actions": [
            {"entity_id": "light.living_main", "service": "light.turn_on", "parameters": {"brightness": 100}}
        ],
        "clarification_questions": [],
        "risk_acknowledgements": [],
    }

    class FakeClient:
        def chat(self, _payload):
            return {"message": {"content": json.dumps(proposal)}}

        def model_digest(self, _model):
            return "test-digest"

        def version(self):
            return "test-version"

    result = compile_request(case["user_request"], inventory, client=FakeClient())
    assert result.run.parse_status == "grounding_block"
    assert result.ir is not None
    assert result.ir.clarification_questions
    assert not result.ir.actions
    assert has_blocking_issues(validate_automation(result.ir, inventory))
