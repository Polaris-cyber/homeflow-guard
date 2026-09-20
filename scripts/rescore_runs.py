"""Recompute metrics from immutable saved model outputs without rerunning a model."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeflow.evaluation import aggregate_scores, load_cases, score_prediction  # noqa: E402
from homeflow.exporter import static_yaml_check, yaml_to_ir  # noqa: E402
from homeflow.io_utils import load_inventory  # noqa: E402
from homeflow.models import AutomationIR  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-version", required=True)
    parser.add_argument("--pipeline", choices=["guarded", "baseline"], default="guarded")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    args = parser.parse_args()

    split = None if args.split == "all" else args.split
    cases = load_cases(ROOT / "data" / "gold_cases.jsonl", split=split)
    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    run_dir = ROOT / "artifacts" / "model_runs" / args.run_version
    rows = []
    missing = []
    for case in cases:
        path = run_dir / f"{case['id']}-{args.pipeline}.json"
        if not path.exists():
            missing.append(case["id"])
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        run = payload.get("run", {})
        raw_output = payload.get("raw_output", "")
        yaml_valid_override = None
        try:
            if args.pipeline == "guarded":
                if payload.get("effective_ir") is not None:
                    predicted_ir = AutomationIR.model_validate(payload["effective_ir"])
                elif run.get("parse_status") == "normalized":
                    partial = json.loads(raw_output)
                    partial.update(triggers=[], conditions=[], actions=[], risk_acknowledgements=[])
                    predicted_ir = AutomationIR.model_validate(partial)
                else:
                    predicted_ir = AutomationIR.model_validate_json(raw_output)
            else:
                predicted_ir = yaml_to_ir(raw_output)
                yaml_valid_override = static_yaml_check(raw_output)[0]
        except ValueError:
            predicted_ir = None
        rows.append(
            score_prediction(
                case,
                predicted_ir,
                inventory,
                schema_success=run.get("parse_status") == "success" and predicted_ir is not None,
                latency_ms=run.get("latency_ms"),
                yaml_valid_override=yaml_valid_override,
            )
        )
    if missing:
        raise SystemExit("Missing saved runs: " + ", ".join(missing))

    report = {
        "rescored_at": datetime.now(timezone.utc).isoformat(),
        "source_run_version": args.run_version,
        "split": args.split,
        "sample_size": len(rows),
        "pipeline": args.pipeline,
        "summary": aggregate_scores(rows, label=f"replay:{args.run_version}:{args.pipeline}"),
        "note": "Metrics recomputed from saved immutable outputs; no model call was made.",
    }
    target = ROOT / "artifacts" / "evaluations" / f"rescored-{args.run_version}-{args.pipeline}-{args.split}"
    Path(f"{target}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with Path(f"{target}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
