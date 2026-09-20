import json
from pathlib import Path

from homeflow.evaluation import aggregate_scores, load_cases, score_prediction, validate_dataset
from homeflow.io_utils import load_inventory
from homeflow.models import AutomationIR
from scripts.evaluate import verify_frozen_inputs


ROOT = Path(__file__).resolve().parents[1]


def test_dataset_shape_and_review_status():
    cases = load_cases(ROOT / "data" / "gold_cases.jsonl")
    assert len(cases) == 50
    assert sum(item["split"] == "dev" for item in cases) == 15
    assert sum(item["split"] == "test" for item in cases) == 35
    assert not validate_dataset(cases)
    statuses = {item["review_status"] for item in cases}
    assert statuses in ({"pending_user_review"}, {"user_reviewed"})


def test_all_frozen_public_demo_rules_load_under_current_schema():
    cases = json.loads((ROOT / "data" / "demo_model_cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 8
    for case in cases:
        AutomationIR.model_validate(case["ir"])
        assert case["model_run"]["model_digest"]


def test_reference_fixture_scores_expected_pipeline_behavior():
    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    cases = load_cases(ROOT / "data" / "gold_cases.jsonl", split="dev")
    rows = [
        score_prediction(
            case,
            AutomationIR.model_validate(case["expected_ir"]),
            inventory,
            schema_success=True,
        )
        for case in cases
    ]
    summary = aggregate_scores(rows, label="reference_fixture_not_model")
    assert summary["sample_size"] == 15
    assert summary["schema_success_rate"] == 1
    assert summary["mean_slot_f1"] == 1
    assert summary["slot_micro_f1"] == 1
    assert summary["unsafe_block_recall"] == 1
    assert summary["risk_code_recall"] == 1
    assert summary["unknown_false_accept_count"] == 0


def test_direct_yaml_baseline_cannot_borrow_guarded_export_validity():
    inventory = load_inventory(ROOT / "data" / "sample_home.yaml")
    case = load_cases(ROOT / "data" / "gold_cases.jsonl", split="dev")[0]
    row = score_prediction(
        case,
        AutomationIR.model_validate(case["expected_ir"]),
        inventory,
        schema_success=True,
        yaml_valid_override=False,
    )
    assert row["slot_f1"] == 1
    assert row["yaml_valid"] is False
    assert row["end_to_end_success"] is False


def test_missing_ir_is_not_unknown_entity_false_accept(inventory):
    case = next(item for item in load_cases(ROOT / "data" / "gold_cases.jsonl") if item["id"] == "U01")
    row = score_prediction(case, None, inventory, schema_success=False)
    assert row["unknown_false_accept"] is False
    assert row["unsafe_blocked"] is False


def test_missing_ir_counts_expected_slots_as_false_negatives(inventory):
    case = next(item for item in load_cases(ROOT / "data" / "gold_cases.jsonl") if item["id"] == "S01")
    row = score_prediction(case, None, inventory, schema_success=False)
    assert row["slot_tp"] == 0
    assert row["slot_fn"] > 0
    assert aggregate_scores([row], label="test")["slot_micro_f1"] == 0


def test_frozen_test_run_rejects_post_test_workflow_change():
    digest = "bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8"
    assert any(
        "prompt_version:" in item
        for item in verify_frozen_inputs("qwen3:14b-q4_K_M", digest)
    )
    assert any("model:" in item for item in verify_frozen_inputs("other:model", digest))
