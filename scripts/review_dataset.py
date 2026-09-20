"""Export and apply a human-review sheet for the synthetic benchmark."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "gold_cases.jsonl"
REVIEW_SHEET = ROOT / "data" / "review_sheet.csv"
FIELDS = [
    "id",
    "split",
    "category",
    "user_request",
    "expected_clarification",
    "risk_labels",
    "expected_ir",
    "decision",
    "reviewer_notes",
]
REVIEW_PAYLOAD_FIELDS = FIELDS[:-2]


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def _case_row(case: dict) -> dict[str, str]:
    return {
        "id": case["id"],
        "split": case["split"],
        "category": case["category"],
        "user_request": case["user_request"],
        "expected_clarification": json.dumps(case["expected_clarification"], ensure_ascii=False),
        "risk_labels": json.dumps(case["risk_labels"], ensure_ascii=False),
        "expected_ir": json.dumps(case["expected_ir"], ensure_ascii=False, separators=(",", ":")),
        "decision": "",
        "reviewer_notes": "",
    }


def _read_sheet() -> list[dict[str, str]]:
    with REVIEW_SHEET.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise SystemExit("Review sheet columns changed. Restore the required column names and order.")
        return list(reader)


def _payload_matches(row: dict[str, str], expected: dict[str, str]) -> bool:
    if any(row[field] != expected[field] for field in REVIEW_PAYLOAD_FIELDS[:4]):
        return False
    try:
        return all(
            json.loads(row[field]) == json.loads(expected[field])
            for field in REVIEW_PAYLOAD_FIELDS[4:]
        )
    except (TypeError, ValueError):
        return False


def _write_sheet(rows: list[dict[str, str]]) -> None:
    temporary = REVIEW_SHEET.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(REVIEW_SHEET)


def export_sheet() -> None:
    cases = load_cases()
    _write_sheet([_case_row(case) for case in cases])
    print(f"Exported {len(cases)} rows to {REVIEW_SHEET}")


def refresh_sheet() -> None:
    """Carry forward only approvals whose full case payload did not change."""
    cases = load_cases()
    previous = _read_sheet()
    by_id = {row["id"]: row for row in previous}
    if len(previous) != len(cases) or len(by_id) != len(previous) or set(by_id) != {case["id"] for case in cases}:
        raise SystemExit("Review sheet IDs do not exactly match the benchmark. Preserve the original and re-export.")
    refreshed: list[dict[str, str]] = []
    carried = 0
    unresolved: list[str] = []
    for case in cases:
        row = _case_row(case)
        old = by_id[case["id"]]
        same_payload = _payload_matches(old, row)
        if old["decision"].strip() == "needs_revision" and same_payload:
            unresolved.append(case["id"])
        if old["decision"].strip() == "approved" and same_payload:
            row["decision"] = "approved"
            carried += 1
        row["reviewer_notes"] = old["reviewer_notes"]
        refreshed.append(row)
    if unresolved:
        raise SystemExit("Rows marked needs_revision were not changed: " + ", ".join(unresolved))
    _write_sheet(refreshed)
    print(f"Carried forward {carried} unchanged approvals; {len(cases) - carried} rows need review.")


def apply_sheet() -> None:
    cases = load_cases()
    by_id = {case["id"]: case for case in cases}
    rows = _read_sheet()

    if len(rows) != len(cases) or len({row["id"] for row in rows}) != len(rows) or {row["id"] for row in rows} != set(by_id):
        raise SystemExit("Review sheet IDs do not exactly match the benchmark. Re-export the sheet.")

    stale = [row["id"] for row in rows if not _payload_matches(row, _case_row(by_id[row["id"]]))]
    if stale:
        raise SystemExit("Review sheet content differs from benchmark. Re-review: " + ", ".join(stale))

    invalid = [row["id"] for row in rows if row["decision"].strip() not in {"approved", "needs_revision"}]
    if invalid:
        raise SystemExit(f"Every row needs a decision. Missing/invalid: {', '.join(invalid)}")

    revision = [row["id"] for row in rows if row["decision"].strip() == "needs_revision"]
    if revision:
        raise SystemExit(
            "Revise the dataset and re-export before approval. Rows needing revision: " + ", ".join(revision)
        )

    for row in rows:
        case = by_id[row["id"]]
        case["review_status"] = "user_reviewed"
        case["reviewer_notes"] = row["reviewer_notes"].strip()

    DATASET.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False, separators=(",", ":")) for case in cases) + "\n",
        encoding="utf-8",
    )
    print(f"Applied human review to {len(cases)} rows in {DATASET}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "refresh", "apply"])
    args = parser.parse_args()
    if args.command == "export":
        export_sheet()
    elif args.command == "refresh":
        refresh_sheet()
    else:
        apply_sheet()


if __name__ == "__main__":
    main()
