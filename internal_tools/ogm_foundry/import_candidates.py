"""Import manually submitted candidate sources from CSV into the Foundry queue."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from internal_tools.ogm_foundry.config import FoundryConfig
from internal_tools.ogm_foundry.workspace_spec import CANDIDATE_REQUIRED_FIELDS, CANDIDATE_TEMPLATE_FIELDS
from internal_tools.ogm_milestone_001.candidate_queue import CandidateIntakeQueue
from internal_tools.ogm_milestone_001.records import OperationalRecords
from internal_tools.ogm_milestone_001.source_taxonomy import normalize_candidate_taxonomy


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_candidate_row(row: dict[str, str], *, row_number: int) -> dict[str, Any]:
    normalized = {key: _clean(row.get(key)) for key in CANDIDATE_TEMPLATE_FIELDS}
    missing = [field for field in CANDIDATE_REQUIRED_FIELDS if not normalized.get(field)]
    if missing:
        raise ValueError(f"row {row_number}: missing required fields: {', '.join(missing)}")
    if not normalized.get("source_authority_type") and not normalized.get("source_type"):
        raise ValueError(
            f"row {row_number}: requires source_authority_type or legacy source_type"
        )
    if not normalized.get("url") and not normalized.get("local_file_path"):
        raise ValueError(f"row {row_number}: requires url or local_file_path")

    taxonomy = normalize_candidate_taxonomy(
        source_type=normalized.get("source_type"),
        source_format=normalized.get("source_format"),
        source_authority_type=normalized.get("source_authority_type"),
        publication_status=normalized.get("publication_status"),
        license_status=normalized.get("license_status"),
        local_file_path=normalized.get("local_file_path"),
        url=normalized.get("url"),
        notes=normalized.get("notes"),
    )

    payload: dict[str, Any] = {
        "title": normalized["title"],
        "publisher": normalized["publisher"],
        "source_type": taxonomy["source_type"],
        "source_format": taxonomy["source_format"],
        "source_authority_type": taxonomy["source_authority_type"],
        "publication_status": taxonomy["publication_status"],
        "submitted_by": normalized["submitted_by"],
        "mission_id": normalized["mission_id"],
        "coverage_object_id": normalized["coverage_object_id"],
        "proposed_canonical_reference_type": normalized["proposed_canonical_reference_type"],
        "notes": normalized.get("notes"),
        "license_status": normalized.get("license_status"),
        "license_notes": normalized.get("license_notes"),
        "authority_reason": normalized.get("authority_reason"),
        "risk_notes": normalized.get("risk_notes"),
    }
    if normalized.get("url"):
        payload["url"] = normalized["url"]
    if normalized.get("local_file_path"):
        payload["local_file_path"] = normalized["local_file_path"]
    if normalized.get("authority_score"):
        payload["authority_score"] = float(normalized["authority_score"])
    return payload


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV file has no header row")
        rows: list[dict[str, str]] = []
        for row in reader:
            if not any((value or "").strip() for value in row.values()):
                continue
            rows.append({key: value or "" for key, value in row.items()})
        return rows


def import_candidates(
    csv_path: Path,
    config: FoundryConfig,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    if not config.intake_db.is_file():
        raise RuntimeError(
            "Intake database not found. Bootstrap the workspace first:\n"
            "  python3 -m internal_tools.ogm_foundry.bootstrap_workspace"
        )

    rows = read_csv_rows(csv_path)
    if not rows:
        raise ValueError("CSV file contains no candidate rows")

    records = OperationalRecords(config.intake_db)
    queue = CandidateIntakeQueue(config.intake_db, records=records)

    created: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = []

    for index, row in enumerate(rows, start=2):
        try:
            payload = parse_candidate_row(row, row_number=index)
            records.get_mission(payload["mission_id"])
            if dry_run:
                created.append(f"dry-run-row-{index}")
                continue
            candidate = queue.submit_candidate(**payload)
            created.append(candidate["candidate_id"])
            if candidate.get("duplicate_of_candidate_id"):
                duplicates.append(candidate["candidate_id"])
        except Exception as exc:
            errors.append(str(exc))

    approvals = records.list_human_approvals()
    sources_exist = config.intake_db.is_file() and _source_count(config.intake_db) > 0

    return {
        "csv_path": str(csv_path),
        "rows_processed": len(rows),
        "candidates_created": len(created),
        "duplicate_candidates": len(duplicates),
        "errors": errors,
        "dry_run": dry_run,
        "human_approvals_created": 0,
        "existing_human_approvals": len(approvals),
        "vault_sources_present": sources_exist,
    }


def _source_count(intake_db: Path) -> int:
    import sqlite3

    try:
        with sqlite3.connect(intake_db) as conn:
            row = conn.execute("SELECT COUNT(*) FROM sources").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import candidate sources from CSV into the Foundry queue.")
    parser.add_argument("csv_path", type=Path, help="Path to candidates.csv")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSV rows without submitting candidates.",
    )
    args = parser.parse_args(argv)
    config = FoundryConfig.from_env()

    try:
        result = import_candidates(args.csv_path, config, dry_run=args.dry_run)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result["errors"]:
        return 1
    print("Candidates were submitted only. No approvals or vault intake were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
