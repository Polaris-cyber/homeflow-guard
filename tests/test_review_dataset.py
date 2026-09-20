import csv
import json

import pytest

from scripts import review_dataset


def _case(case_id: str, request: str) -> dict:
    return {
        "id": case_id,
        "split": "dev",
        "category": "simple_valid",
        "user_request": request,
        "expected_clarification": False,
        "risk_labels": [],
        "expected_ir": {"name": request},
        "review_status": "pending_user_review",
    }


def _prepare(monkeypatch, tmp_path, cases: list[dict], previous_rows: list[dict]) -> None:
    dataset = tmp_path / "gold_cases.jsonl"
    review = tmp_path / "review_sheet.csv"
    dataset.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n", encoding="utf-8")
    with review.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_dataset.FIELDS)
        writer.writeheader()
        writer.writerows(previous_rows)
    monkeypatch.setattr(review_dataset, "DATASET", dataset)
    monkeypatch.setattr(review_dataset, "REVIEW_SHEET", review)


def test_refresh_only_carries_unchanged_approvals(monkeypatch, tmp_path):
    cases = [_case("S01", "原需求"), _case("S02", "修订后需求")]
    unchanged = review_dataset._case_row(cases[0])
    unchanged["decision"] = "approved"
    old_revision = review_dataset._case_row(_case("S02", "原需求"))
    old_revision["decision"] = "needs_revision"
    old_revision["reviewer_notes"] = "请修订"
    _prepare(monkeypatch, tmp_path, cases, [unchanged, old_revision])

    review_dataset.refresh_sheet()
    rows = review_dataset._read_sheet()
    assert [row["decision"] for row in rows] == ["approved", ""]
    assert rows[1]["reviewer_notes"] == "请修订"


def test_apply_rejects_stale_review_content(monkeypatch, tmp_path):
    case = _case("S01", "修订后需求")
    stale = review_dataset._case_row(_case("S01", "原需求"))
    stale["decision"] = "approved"
    _prepare(monkeypatch, tmp_path, [case], [stale])

    with pytest.raises(SystemExit, match="content differs"):
        review_dataset.apply_sheet()
    assert review_dataset.load_cases()[0]["review_status"] == "pending_user_review"
