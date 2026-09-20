"""Prepare ten reviewed synthetic automations for isolated HA config checks."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeflow.evaluation import load_cases  # noqa: E402
from homeflow.exporter import export_yaml, static_yaml_check  # noqa: E402
from homeflow.io_utils import load_inventory  # noqa: E402
from homeflow.models import AutomationIR  # noqa: E402


CASE_IDS = tuple(f"S{number:02d}" for number in range(1, 11))
OUTPUT = ROOT / "tests" / "ha_config" / "automations.yaml"


def main() -> None:
    cases = {case["id"]: case for case in load_cases(ROOT / "data" / "gold_cases.jsonl")}
    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    automations: list[dict] = []
    for case_id in CASE_IDS:
        case = cases[case_id]
        if case["review_status"] != "user_reviewed":
            raise SystemExit(f"Case {case_id} has not been reviewed.")
        ir = AutomationIR.model_validate(case["expected_ir"])
        content = export_yaml(ir, inventory)
        valid, errors = static_yaml_check(content)
        if not valid:
            raise SystemExit(f"Case {case_id} failed static check: {errors}")
        automations.append(yaml.safe_load(content))
    OUTPUT.write_text(
        yaml.safe_dump(automations, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"Prepared {len(automations)} reviewed synthetic automations in {OUTPUT}")


if __name__ == "__main__":
    main()
