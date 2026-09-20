"""Freeze eight actual guarded-model runs for the public offline demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeflow.evaluation import load_cases  # noqa: E402
from homeflow.io_utils import load_inventory  # noqa: E402
from homeflow.models import AutomationIR  # noqa: E402
from homeflow.validator import validate_automation  # noqa: E402


SELECTED_IDS = ["S01", "S02", "M01", "M02", "A01", "U01", "R01", "R03"]
OUTPUT = ROOT / "data" / "demo_model_cases.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-version", default="compiler-dev-v0.8")
    args = parser.parse_args()
    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    cases = {item["id"]: item for item in load_cases(ROOT / "data" / "gold_cases.jsonl")}
    frozen = []
    missing = []
    for case_id in SELECTED_IDS:
        run_path = ROOT / "artifacts" / "model_runs" / args.prompt_version / f"{case_id}-guarded.json"
        if not run_path.exists():
            missing.append(case_id)
            continue
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        ir = AutomationIR.model_validate_json(payload["raw_output"])
        frozen.append(
            {
                "id": case_id,
                "category": cases[case_id]["category"],
                "user_request": cases[case_id]["user_request"],
                "ir": ir.model_dump(mode="json"),
                "validation_issues": [issue.model_dump(mode="json") for issue in validate_automation(ir, inventory)],
                "model_run": payload["run"],
                "source_note": "Actual local Ollama run; synthetic input; not a user-study result.",
            }
        )
    if missing:
        raise SystemExit("Run the guarded dev evaluation first. Missing: " + ", ".join(missing))
    OUTPUT.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(frozen)} actual model runs to {OUTPUT}")


if __name__ == "__main__":
    main()
