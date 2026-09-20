from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SUPPORTED_DOMAINS = {
    "light",
    "climate",
    "cover",
    "media_player",
    "lock",
    "binary_sensor",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class Device(StrictModel):
    entity_id: str
    domain: str
    area: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)
    allowed_services: list[str] = Field(default_factory=list)
    parameter_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    sensitivity: Literal["normal", "sensitive"] = "normal"

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if value.count(".") != 1:
            raise ValueError("entity_id 必须采用 domain.object_id 格式")
        domain, object_id = value.split(".", 1)
        if domain not in SUPPORTED_DOMAINS:
            raise ValueError(f"不支持的设备域：{domain}")
        if not object_id or not object_id.replace("_", "").isalnum():
            raise ValueError("entity_id 只能包含字母、数字和下划线")
        return value

    @model_validator(mode="after")
    def entity_domain_must_match(self) -> "Device":
        if self.entity_id.split(".", 1)[0] != self.domain:
            raise ValueError("domain 必须与 entity_id 前缀一致")
        return self


class DeviceInventory(StrictModel):
    inventory_id: str
    title: str
    devices: list[Device]
    provenance: str = "synthetic"

    @model_validator(mode="after")
    def validate_inventory(self) -> "DeviceInventory":
        if not self.devices:
            raise ValueError("设备清单不能为空")
        if len(self.devices) > 100:
            raise ValueError("设备数量不能超过 100")
        ids = [device.entity_id for device in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("设备清单中存在重复 entity_id")
        return self

    def by_id(self) -> dict[str, Device]:
        return {device.entity_id: device for device in self.devices}


class TimeTrigger(StrictModel):
    trigger_type: Literal["time"]
    at: str


class StateTrigger(StrictModel):
    trigger_type: Literal["state"]
    entity_id: str
    from_state: str | None = None
    to_state: str


class NumericStateTrigger(StrictModel):
    trigger_type: Literal["numeric_state"]
    entity_id: str
    above: float | None = None
    below: float | None = None
    attribute: str | None = None

    @model_validator(mode="after")
    def threshold_required(self) -> "NumericStateTrigger":
        if self.above is None and self.below is None:
            raise ValueError("数值触发器至少需要 above 或 below")
        return self


class SunTrigger(StrictModel):
    trigger_type: Literal["sun"]
    event: Literal["sunrise", "sunset"]
    offset: str | None = None


class ManualTrigger(StrictModel):
    trigger_type: Literal["manual"]


Trigger = Annotated[
    TimeTrigger | StateTrigger | NumericStateTrigger | SunTrigger | ManualTrigger,
    Field(discriminator="trigger_type"),
]


class TimeCondition(StrictModel):
    condition_type: Literal["time"]
    after: str | None = None
    before: str | None = None

    @model_validator(mode="after")
    def time_bound_required(self) -> "TimeCondition":
        if self.after is None and self.before is None:
            raise ValueError("时间条件至少需要 after 或 before")
        return self


class StateCondition(StrictModel):
    condition_type: Literal["state"]
    entity_id: str
    state: str


class NumericStateCondition(StrictModel):
    condition_type: Literal["numeric_state"]
    entity_id: str
    above: float | None = None
    below: float | None = None
    attribute: str | None = None

    @model_validator(mode="after")
    def threshold_required(self) -> "NumericStateCondition":
        if self.above is None and self.below is None:
            raise ValueError("数值条件至少需要 above 或 below")
        return self


Condition = Annotated[
    TimeCondition | StateCondition | NumericStateCondition,
    Field(discriminator="condition_type"),
]


class Action(StrictModel):
    entity_id: str
    service: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AutomationIR(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    triggers: list[Trigger]
    conditions: list[Condition]
    actions: list[Action]
    clarification_questions: list[str]
    risk_acknowledgements: list[str]

    @model_validator(mode="after")
    def validate_shape(self) -> "AutomationIR":
        if self.clarification_questions and (self.triggers or self.conditions or self.actions):
            raise ValueError("需要澄清时不能保留触发器、条件或动作")
        if not self.triggers and not self.clarification_questions:
            raise ValueError("必须提供触发器，或明确列出需要澄清的问题")
        if not self.actions and not self.clarification_questions:
            raise ValueError("必须提供动作，或明确列出需要澄清的问题")
        return self


class ValidationIssue(StrictModel):
    code: str
    severity: Severity
    path: str
    message: str
    requires_confirmation: bool = False
    acknowledgement_key: str | None = None


class EntityState(StrictModel):
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class SimulationInput(StrictModel):
    now_time: str = "19:00:00"
    sun_event: Literal["sunrise", "sunset"] | None = None
    manual: bool = False
    states: dict[str, EntityState] = Field(default_factory=dict)


class TraceStep(StrictModel):
    step: int
    stage: Literal["validation", "trigger", "condition", "action", "result"]
    status: Literal["passed", "failed", "blocked", "skipped"]
    message: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class SimulationResult(StrictModel):
    status: Literal["executed", "not_triggered", "conditions_failed", "blocked"]
    initial_states: dict[str, EntityState]
    final_states: dict[str, EntityState]
    trace: list[TraceStep]


class ModelRun(StrictModel):
    model: str
    model_digest: str | None = None
    ollama_version: str | None = None
    prompt_version: str
    schema_version: str
    generation_config: dict[str, Any]
    requested_at: datetime
    latency_ms: int
    raw_output_sha256: str
    attempt_output_sha256: list[str]
    retries: int
    parse_status: Literal["success", "normalized", "failed"]
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


class CompilationResult(StrictModel):
    ir: AutomationIR | None
    run: ModelRun
    raw_output: str
