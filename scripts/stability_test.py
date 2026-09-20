"""Run 10 synthetic stress cases three times and record semantic stability."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeflow.compiler import OllamaClient, compile_request  # noqa: E402
from homeflow.evaluation import load_cases  # noqa: E402
from homeflow.io_utils import load_inventory  # noqa: E402


CASE_IDS = ["S01", "S02", "M01", "M02", "A01", "A02", "U01", "U02", "R01", "R02"]
OUTPUT = ROOT / "artifacts" / "latest_stability.json"


def semantic_hash(ir: object) -> str:
    payload = json.dumps(ir, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:14b-q4_K_M")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 2:
        raise SystemExit("repeats must be at least 2")

    if not OllamaClient().version():
        raise SystemExit("Ollama service is unavailable; no stability run was started.")

    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    cases = {item["id"]: item for item in load_cases(ROOT / "data" / "gold_cases.jsonl")}
    records = []
    for case_id in CASE_IDS:
        for repeat in range(1, args.repeats + 1):
            result = compile_request(cases[case_id]["user_request"], inventory, model=args.model)
            records.append(
                {
                    "case_id": case_id,
                    "repeat": repeat,
                    "schema_success": result.ir is not None,
                    "semantic_hash": semantic_hash(result.ir.model_dump(mode="json")) if result.ir else None,
                    "raw_output_sha256": result.run.raw_output_sha256,
                    "latency_ms": result.run.latency_ms,
                    "model_digest": result.run.model_digest,
                    "prompt_version": result.run.prompt_version,
                    "schema_version": result.run.schema_version,
                    "error": result.run.error,
                }
            )

    per_case = []
    for case_id in CASE_IDS:
        case_rows = [row for row in records if row["case_id"] == case_id]
        successful_hashes = [row["semantic_hash"] for row in case_rows if row["semantic_hash"]]
        most_common = Counter(successful_hashes).most_common(1)
        per_case.append(
            {
                "case_id": case_id,
                "schema_success_rate": sum(row["schema_success"] for row in case_rows) / len(case_rows),
                "semantic_stability_rate": most_common[0][1] / len(case_rows) if most_common else 0.0,
                "unique_semantic_outputs": len(set(successful_hashes)),
            }
        )

    latencies = [row["latency_ms"] for row in records]
    first_record = records[0]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "model_digest": first_record["model_digest"],
        "prompt_version": first_record["prompt_version"],
        "schema_version": first_record["schema_version"],
        "case_count": len(CASE_IDS),
        "repeats": args.repeats,
        "definition": "Per-case share of all runs matching the most common normalized AutomationIR.",
        "mean_semantic_stability_rate": sum(item["semantic_stability_rate"] for item in per_case) / len(per_case),
        "schema_success_rate": sum(row["schema_success"] for row in records) / len(records),
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": sorted(latencies)[max(0, round(0.95 * len(latencies)) - 1)],
        "per_case": per_case,
        "records": records,
        "scope_note": "Synthetic development cases; not a user-study result.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
