from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeflow.compiler import (  # noqa: E402
    PROMPT_VERSION,
    SCHEMA_VERSION,
    CompilerError,
    OllamaClient,
    baseline_yaml,
    compile_request,
)
from homeflow.evaluation import aggregate_scores, load_cases, score_prediction, validate_dataset  # noqa: E402
from homeflow.exporter import static_yaml_check, yaml_to_ir  # noqa: E402
from homeflow.io_utils import load_inventory  # noqa: E402
from homeflow.models import AutomationIR  # noqa: E402


def verify_frozen_inputs(model: str, digest: str | None) -> list[str]:
    manifest = json.loads((ROOT / "artifacts" / "freeze_v1.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for key, actual in (
        ("prompt_version", PROMPT_VERSION),
        ("schema_version", SCHEMA_VERSION),
        ("model", model),
        ("model_digest", digest),
    ):
        if manifest[key] != actual:
            errors.append(f"{key}: frozen={manifest[key]}, current={actual}")
    for relative, expected_hash in manifest["sha256"].items():
        actual_hash = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            errors.append(f"{relative}: SHA256 changed")
    return errors


def write_rows(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_run(
    case_id: str,
    pipeline: str,
    raw_output: str,
    metadata: dict,
    effective_ir: AutomationIR | None = None,
) -> None:
    version = str(metadata.get("prompt_version", "unknown")).replace("/", "-").replace("\\", "-")
    target = ROOT / "artifacts" / "model_runs" / version / f"{case_id}-{pipeline}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "pipeline": pipeline,
                "raw_output": raw_output,
                "effective_ir": effective_ir.model_dump(mode="json") if effective_ir else None,
                "run": metadata,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate HomeFlow Guard on the synthetic benchmark.")
    parser.add_argument("--mode", choices=["fixture", "ollama"], default="fixture")
    parser.add_argument("--pipeline", choices=["guarded", "baseline", "both"], default="guarded")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--model", default="qwen3:14b-q4_K_M")
    parser.add_argument("--allow-pending-labels", action="store_true")
    args = parser.parse_args()

    if args.mode == "ollama" and args.split == "all":
        print("正式模型评测只能选择 dev 或 test；不能用 all 混合开发集与锁定测试集。")
        return 7

    split = None if args.split == "all" else args.split
    all_cases = load_cases(ROOT / "data" / "gold_cases.jsonl")
    errors = validate_dataset(all_cases)
    if errors:
        print(json.dumps({"dataset_errors": errors}, ensure_ascii=False, indent=2))
        return 2
    cases = [item for item in all_cases if split is None or item["split"] == split]
    pending = [item["id"] for item in cases if item["review_status"] != "user_reviewed"]
    formal_model_run = args.mode == "ollama" and args.split in {"test", "all"}
    if pending and (formal_model_run or not args.allow_pending_labels):
        print(
            "评测集尚未逐条人工复核。只有开发集或 fixture 自检可使用 --allow-pending-labels；"
            "35 条测试集不能绕过人工复核。"
        )
        return 3
    if formal_model_run and PROMPT_VERSION != "compiler-v1.0":
        print("正式测试前必须先审核并冻结 Prompt 为 compiler-v1.0；当前版本：" + PROMPT_VERSION)
        return 6
    if args.mode == "fixture" and args.pipeline != "guarded":
        print("fixture 模式只用于验证 guarded 评测管线，不能作为基线或模型结果。")
        return 4

    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    pipelines = ["guarded", "baseline"] if args.pipeline == "both" else [args.pipeline]
    summaries = []
    all_rows: dict[str, list[dict]] = {}
    current_run_versions: set[str] = set()
    current_schema_versions: set[str] = set()
    client = OllamaClient()
    if args.mode == "ollama" and not client.version():
        print("Ollama 服务不可用；评测未开始。请先启动 Ollama，再重试。")
        return 5
    if formal_model_run:
        freeze_errors = verify_frozen_inputs(args.model, client.model_digest(args.model))
        if freeze_errors:
            print("冻结输入与当前环境不一致，拒绝运行测试集：" + "; ".join(freeze_errors))
            return 8

    for pipeline in pipelines:
        rows = []
        for item in cases:
            predicted_ir = None
            schema_success = False
            latency_ms = None
            yaml_valid_override = None
            raw_yaml = ""
            run = None
            if args.mode == "fixture":
                predicted_ir = AutomationIR.model_validate(item["expected_ir"])
                schema_success = True
            elif pipeline == "guarded":
                try:
                    result = compile_request(item["user_request"], inventory, model=args.model, client=client)
                    predicted_ir = result.ir
                    schema_success = result.run.parse_status in {"success", "grounding_block"}
                    latency_ms = result.run.latency_ms
                    current_run_versions.add(result.run.prompt_version)
                    current_schema_versions.add(result.run.schema_version)
                    save_run(
                        item["id"], pipeline, result.raw_output, result.run.model_dump(mode="json"), result.ir
                    )
                except CompilerError as exc:
                    save_run(item["id"], pipeline, str(exc), {"error": str(exc)})
            else:
                try:
                    raw_yaml, run = baseline_yaml(item["user_request"], inventory, model=args.model, client=client)
                    latency_ms = run.latency_ms
                    predicted_ir = yaml_to_ir(raw_yaml)
                    schema_success = True
                    current_run_versions.add(run.prompt_version)
                    current_schema_versions.add(run.schema_version)
                    yaml_valid_override = static_yaml_check(raw_yaml)[0]
                    save_run(item["id"], pipeline, raw_yaml, run.model_dump(mode="json"))
                except (CompilerError, ValueError, KeyError) as exc:
                    schema_success = False
                    if run is not None:
                        metadata = run.model_dump(mode="json")
                        metadata["conversion_error"] = str(exc)
                        save_run(item["id"], pipeline, raw_yaml, metadata)
                    else:
                        save_run(item["id"], pipeline, str(exc), {"error": str(exc)})
            rows.append(
                score_prediction(
                    item,
                    predicted_ir,
                    inventory,
                    schema_success=schema_success,
                    latency_ms=latency_ms,
                    yaml_valid_override=yaml_valid_override,
                )
            )
        label = "reference_fixture_not_model" if args.mode == "fixture" else f"{pipeline}:{args.model}"
        summaries.append(aggregate_scores(rows, label=label))
        all_rows[pipeline] = rows

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "model": args.model if args.mode == "ollama" else None,
        "split": args.split,
        "dataset_reviewed": not pending,
        "pending_review_count": len(pending),
        "sample_size": len(cases),
        "summaries": summaries,
        "claim_warning": (
            "Fixture results only validate scoring code and must not be presented as model performance."
            if args.mode == "fixture"
            else "Model results describe only this synthetic benchmark and hardware run."
        ),
    }
    report["prompt_versions"] = sorted(current_run_versions)
    report["schema_versions"] = sorted(current_schema_versions)
    if len(summaries) == 2:
        report["end_to_end_improvement_points"] = round(
            (summaries[0]["end_to_end_success_rate"] - summaries[1]["end_to_end_success_rate"]) * 100,
            2,
        )
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "latest_evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    flat_rows = []
    for pipeline, rows in all_rows.items():
        flat_rows.extend({"pipeline": pipeline, **row} for row in rows)
    write_rows(flat_rows, artifact_dir / "latest_evaluation.csv")
    archive_dir = artifact_dir / "evaluations"
    archive_dir.mkdir(exist_ok=True)
    stamp = report["generated_at"].replace(":", "-")
    archive_stem = f"{stamp}-{args.mode}-{args.split}-{'-'.join(pipelines)}"
    (archive_dir / f"{archive_stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_rows(flat_rows, archive_dir / f"{archive_stem}.csv")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
