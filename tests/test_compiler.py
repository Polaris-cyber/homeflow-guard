import json

import pytest
from pydantic import ValidationError

from homeflow.compiler import _request_payload, compile_request
from homeflow.models import AutomationIR


def test_clarification_cannot_contain_partial_rule():
    with pytest.raises(ValidationError, match="需要澄清时不能保留"):
        AutomationIR.model_validate(
            {
                "name": "需要澄清",
                "triggers": [{"trigger_type": "time", "at": "20:00:00"}],
                "conditions": [],
                "actions": [],
                "clarification_questions": ["请提供设备。"],
                "risk_acknowledgements": [],
            }
        )


def test_model_output_schema_requires_explicit_numeric_bounds():
    payload = _request_payload("test-model", "test-system", {"user_request": "test"}, schema=True)
    for name in ("NumericStateTrigger", "NumericStateCondition"):
        required = payload["format"]["$defs"][name]["required"]
        assert "above" in required
        assert "below" in required


def test_numeric_threshold_error_retries_with_explicit_instruction(inventory):
    class FakeClient:
        def __init__(self):
            self.payloads = []

        def chat(self, payload):
            self.payloads.append(payload)
            rule = {
                "name": "日落保暖",
                "triggers": [{"trigger_type": "sun", "event": "sunset"}],
                "conditions": [
                    {
                        "condition_type": "numeric_state",
                        "entity_id": "climate.living_ac",
                        "attribute": "current_temperature",
                    }
                ],
                "actions": [
                    {
                        "entity_id": "climate.living_ac",
                        "service": "climate.set_temperature",
                        "parameters": {"temperature": 22},
                    }
                ],
                "clarification_questions": [],
                "risk_acknowledgements": [],
            }
            if len(self.payloads) == 2:
                rule["conditions"][0]["below"] = 18
            return {"message": {"content": json.dumps(rule)}}

        def model_digest(self, _model):
            return "test-digest"

        def version(self):
            return "test-version"

    client = FakeClient()
    result = compile_request("日落时客厅室温低于18度，把空调设为22度。", inventory, client=client)

    assert result.ir is not None
    assert result.ir.conditions[0].below == 18
    assert result.run.retries == 1
    retry = json.loads(client.payloads[1]["messages"][1]["content"])
    assert "above 或 below" in retry["repair_instruction"]
    assert "validation_error" in retry
    assert "previous_invalid_output" in retry


def test_repeated_partial_clarification_discards_rule(inventory):
    class FakeClient:
        calls = 0

        def chat(self, _payload):
            self.calls += 1
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "name": "需要澄清",
                            "triggers": [{"trigger_type": "time", "at": "20:00:00"}],
                            "conditions": [],
                            "actions": [],
                            "clarification_questions": ["请提供设备。"],
                            "risk_acknowledgements": [],
                        }
                    )
                }
            }

        def model_digest(self, _model):
            return "test-digest"

        def version(self):
            return "test-version"

    client = FakeClient()
    result = compile_request("晚上八点打开厨房风扇。", inventory, client=client)
    assert client.calls == 2
    assert result.run.parse_status == "normalized"
    assert result.ir is not None
    assert result.ir.clarification_questions
    assert not result.ir.triggers
    assert not result.ir.actions
