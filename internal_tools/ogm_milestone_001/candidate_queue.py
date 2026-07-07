"""Controlled candidate intake queue for manual source submissions."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from internal_tools.ogm_milestone_001.records import OperationalRecords
from internal_tools.ogm_milestone_001.schema import migrate_intake_operational_schema
from internal_tools.ogm_milestone_001.source_taxonomy import enrich_candidate_record, normalize_candidate_taxonomy
from internal_tools.ogm_milestone_001.utils import json_dumps, json_loads, prefixed_uuid, sha256_file, utc_now_iso


class CandidateIntakeQueue:
    """Manual-first queue for candidate sources before Curator-001 review."""

    STATUSES = {
        "submitted",
        "under_review",
        "recommended",
        "rejected",
        "approved_for_intake",
        "sent_to_vault",
        "vaulted",
        "bridged_to_repository",
        "failed",
    }

    def __init__(self, db_path: str | Path, records: OperationalRecords | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.records = records or OperationalRecords(self.db_path)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            migrate_intake_operational_schema(conn)

    def submit_candidate(
        self,
        *,
        title: str,
        publisher: str,
        source_type: str,
        submitted_by: str,
        mission_id: str,
        coverage_object_id: str,
        proposed_canonical_reference_type: str,
        url: str | None = None,
        local_file_path: str | Path | None = None,
        notes: str | None = None,
        candidate_id: str | None = None,
        status: str = "submitted",
        license_status: str | None = None,
        license_notes: str | None = None,
        license_source_url: str | None = None,
        license_text_excerpt: str | None = None,
        license_checked_at: str | None = None,
        license_checked_by: str | None = None,
        authority_score: float | None = None,
        authority_reason: str | None = None,
        risk_notes: str | None = None,
        reviewer_notes: str | None = None,
        assigned_reviewer: str | None = None,
        review_due_at: str | None = None,
        review_priority: str | None = None,
        source_format: str | None = None,
        source_authority_type: str | None = None,
        publication_status: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        self.records.get_mission(mission_id)
        self._validate_status(status)
        if authority_score is not None and not 0 <= authority_score <= 1:
            raise ValueError("authority_score must be between 0 and 1")
        if not url and local_file_path is None:
            raise ValueError("candidate requires url or local_file_path")

        file_path = Path(local_file_path) if local_file_path is not None else None
        file_checksum = sha256_file(file_path) if file_path is not None and file_path.is_file() else None
        normalized_url = normalize_url(url) if url else None
        source_location = str(url or file_path)
        now = utc_now_iso()
        candidate_id = candidate_id or prefixed_uuid("cand")

        duplicates = self.find_duplicates(
            title=title,
            publisher=publisher,
            normalized_url=normalized_url,
            file_checksum=file_checksum,
        )
        duplicate_of_candidate_id = duplicates[0]["candidate_id"] if duplicates else None
        taxonomy = normalize_candidate_taxonomy(
            source_type=source_type,
            source_format=source_format,
            source_authority_type=source_authority_type,
            publication_status=publication_status,
            license_status=license_status,
            local_file_path=file_path,
            url=url,
            notes=notes,
            reviewer_notes=reviewer_notes,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_sources (
                    candidate_id, title, publisher, source_location, normalized_url,
                    local_file_path, file_checksum, source_type, submitted_by, submitted_at,
                    mission_id, coverage_object_id, proposed_canonical_reference_type,
                    notes, status, license_status, license_notes, license_source_url,
                    license_text_excerpt, license_checked_at, license_checked_by, authority_score,
                    authority_reason, risk_notes, reviewer_notes, assigned_reviewer,
                    review_due_at, review_priority, duplicate_of_candidate_id,
                    curator_recommendation_id, source_format, source_authority_type,
                    publication_status, metadata_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    title,
                    publisher,
                    source_location,
                    normalized_url,
                    str(file_path) if file_path is not None else None,
                    file_checksum,
                    taxonomy["source_type"],
                    submitted_by,
                    now,
                    mission_id,
                    coverage_object_id,
                    proposed_canonical_reference_type,
                    notes,
                    status,
                    license_status,
                    license_notes,
                    license_source_url,
                    license_text_excerpt,
                    license_checked_at,
                    license_checked_by,
                    authority_score,
                    authority_reason,
                    risk_notes,
                    reviewer_notes,
                    assigned_reviewer,
                    review_due_at,
                    review_priority,
                    duplicate_of_candidate_id,
                    None,
                    taxonomy["source_format"],
                    taxonomy["source_authority_type"],
                    taxonomy["publication_status"],
                    json_dumps({**(metadata or {}), "duplicate_candidates": duplicates}),
                    now,
                ),
            )
        self.record_review_event(
            candidate_id=candidate_id,
            actor=actor or submitted_by,
            from_status=None,
            to_status=status,
            reason="candidate submitted",
            notes=notes,
            metadata={"duplicate_of_candidate_id": duplicate_of_candidate_id},
        )
        return self.get_candidate(candidate_id)

    def find_duplicates(
        self,
        *,
        title: str,
        publisher: str,
        normalized_url: str | None = None,
        file_checksum: str | None = None,
    ) -> list[dict[str, Any]]:
        title_key = normalize_text(title)
        publisher_key = normalize_text(publisher)
        duplicates: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM candidate_sources ORDER BY submitted_at").fetchall()

        for row in rows:
            reasons = []
            if normalized_url and row["normalized_url"] == normalized_url:
                reasons.append("url")
            if file_checksum and row["file_checksum"] == file_checksum:
                reasons.append("file_checksum")
            title_ratio = SequenceMatcher(None, title_key, normalize_text(row["title"])).ratio()
            publisher_ratio = SequenceMatcher(None, publisher_key, normalize_text(row["publisher"])).ratio()
            if title_ratio >= 0.92 and publisher_ratio >= 0.92:
                reasons.append("title_publisher")
            if reasons:
                duplicate = self._candidate_from_row(row)
                duplicate["duplicate_reasons"] = reasons
                duplicates.append(duplicate)
        return duplicates

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM candidate_sources WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown candidate source: {candidate_id}")
        return self._candidate_from_row(row)

    def list_candidates(
        self,
        *,
        mission_id: str | None = None,
        status: str | None = None,
        coverage_object_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if mission_id is not None:
            clauses.append("mission_id = ?")
            params.append(mission_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if coverage_object_id is not None:
            clauses.append("coverage_object_id = ?")
            params.append(coverage_object_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM candidate_sources {where} ORDER BY submitted_at", params).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def update_candidate_review(
        self,
        candidate_id: str,
        *,
        status: str | None = None,
        license_status: str | None = None,
        license_notes: str | None = None,
        license_source_url: str | None = None,
        license_text_excerpt: str | None = None,
        license_checked_at: str | None = None,
        license_checked_by: str | None = None,
        authority_score: float | None = None,
        authority_reason: str | None = None,
        risk_notes: str | None = None,
        reviewer_notes: str | None = None,
        assigned_reviewer: str | None = None,
        review_due_at: str | None = None,
        review_priority: str | None = None,
        curator_recommendation_id: str | None = None,
        actor: str = "system",
        reason: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        before = self.get_candidate(candidate_id)
        if status is not None:
            self._validate_status(status)
        if authority_score is not None and not 0 <= authority_score <= 1:
            raise ValueError("authority_score must be between 0 and 1")
        updates = {
            "status": status,
            "license_status": license_status,
            "license_notes": license_notes,
            "license_source_url": license_source_url,
            "license_text_excerpt": license_text_excerpt,
            "license_checked_at": license_checked_at,
            "license_checked_by": license_checked_by,
            "authority_score": authority_score,
            "authority_reason": authority_reason,
            "risk_notes": risk_notes,
            "reviewer_notes": reviewer_notes,
            "assigned_reviewer": assigned_reviewer,
            "review_due_at": review_due_at,
            "review_priority": review_priority,
            "curator_recommendation_id": curator_recommendation_id,
        }
        set_parts = [f"{column} = ?" for column, value in updates.items() if value is not None]
        params = [value for value in updates.values() if value is not None]
        if not set_parts:
            return self.get_candidate(candidate_id)
        set_parts.append("updated_at = ?")
        params.append(utc_now_iso())
        params.append(candidate_id)
        with self._connect() as conn:
            updated = conn.execute(
                f"UPDATE candidate_sources SET {', '.join(set_parts)} WHERE candidate_id = ?",
                params,
            ).rowcount
        if updated == 0:
            raise KeyError(f"unknown candidate source: {candidate_id}")
        after = self.get_candidate(candidate_id)
        if status is not None or metadata is not None or reason is not None or notes is not None:
            self.record_review_event(
                candidate_id=candidate_id,
                actor=actor,
                from_status=before["status"],
                to_status=after["status"],
                reason=reason,
                notes=notes,
                metadata=metadata or {},
            )
        return after

    def assign_reviewer(
        self,
        candidate_id: str,
        *,
        assigned_reviewer: str,
        review_due_at: str | None = None,
        review_priority: str = "medium",
        actor: str = "system",
        notes: str | None = None,
    ) -> dict[str, Any]:
        return self.update_candidate_review(
            candidate_id,
            assigned_reviewer=assigned_reviewer,
            review_due_at=review_due_at,
            review_priority=review_priority,
            actor=actor,
            reason="reviewer assigned",
            notes=notes,
            metadata={
                "assigned_reviewer": assigned_reviewer,
                "review_due_at": review_due_at,
                "review_priority": review_priority,
            },
        )

    def attach_license_evidence(
        self,
        candidate_id: str,
        *,
        license_status: str,
        license_source_url: str,
        license_text_excerpt: str,
        license_checked_by: str,
        license_notes: str | None = None,
        license_checked_at: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        checked_at = license_checked_at or utc_now_iso()
        return self.update_candidate_review(
            candidate_id,
            license_status=license_status,
            license_source_url=license_source_url,
            license_text_excerpt=license_text_excerpt,
            license_checked_at=checked_at,
            license_checked_by=license_checked_by,
            license_notes=license_notes,
            actor=actor or license_checked_by,
            reason="license evidence captured",
            metadata={
                "license_status": license_status,
                "license_source_url": license_source_url,
                "license_checked_at": checked_at,
                "license_checked_by": license_checked_by,
            },
        )

    def prepare_for_vault_intake(self, candidate_id: str, *, strict_license_review: bool = False) -> dict[str, Any]:
        candidate = self.get_candidate(candidate_id)
        if candidate["status"] != "approved_for_intake":
            raise PermissionError("candidate must be approved_for_intake before source intake")
        approval = self._find_candidate_or_recommendation_approval(candidate)
        local_file_path = candidate.get("local_file_path")
        if not local_file_path or not Path(local_file_path).is_file():
            raise FileNotFoundError("approved candidate requires an existing local file for Raw Source Vault intake")
        license_warning = None
        if not candidate.get("license_status") or not candidate.get("license_checked_by"):
            license_warning = "candidate is missing complete license review evidence"
            if strict_license_review:
                raise ValueError(license_warning)

        enriched = enrich_candidate_record(candidate)
        publication_warning = "; ".join(enriched.get("publication_warnings") or [])
        if enriched.get("publication_status") in {"internal_only", "not_publishable"}:
            publication_warning = publication_warning or f"publication_status={enriched['publication_status']}"

        return {
            "file_path": local_file_path,
            "source": candidate["publisher"],
            "license": candidate["license_status"] or "unknown",
            "mission": candidate["mission_id"],
            "mission_id": candidate["mission_id"],
            "curator": "curator-001",
            "approval_status": "approved",
            "coverage_object_ids": [candidate["coverage_object_id"]],
            "curator_recommendation_id": candidate["curator_recommendation_id"],
            "human_approval_id": approval["approval_id"],
            "source_quality_score": candidate["authority_score"],
            "canonical_reference_type": candidate["proposed_canonical_reference_type"],
            "source_format": enriched["source_format"],
            "source_authority_type": enriched["source_authority_type"],
            "publication_status": enriched["publication_status"],
            "metadata": {
                "candidate_id": candidate_id,
                "candidate_title": candidate["title"],
                "source_location": candidate["source_location"],
                "legacy_source_type": candidate["source_type"],
                "source_format": enriched["source_format"],
                "source_authority_type": enriched["source_authority_type"],
                "publication_status": enriched["publication_status"],
                "canonical_reference_type": candidate["proposed_canonical_reference_type"],
                "pack_ready": enriched.get("pack_ready", False),
                "publication_warnings": enriched.get("publication_warnings") or [],
                "license_notes": candidate["license_notes"],
                "license_source_url": candidate["license_source_url"],
                "license_text_excerpt": candidate["license_text_excerpt"],
                "license_checked_at": candidate["license_checked_at"],
                "license_checked_by": candidate["license_checked_by"],
                "license_warning": license_warning,
                "publication_warning": publication_warning or None,
                "authority_reason": candidate["authority_reason"],
                "risk_notes": candidate["risk_notes"],
                "reviewer_notes": candidate["reviewer_notes"],
            },
        }

    def _find_candidate_or_recommendation_approval(self, candidate: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT approval_id FROM human_approvals
                WHERE decision = 'approved'
                  AND (
                    (target_type = 'candidate_source' AND target_id = ?)
                    OR (target_type = 'source_intake' AND recommendation_id = ?)
                  )
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (candidate["candidate_id"], candidate["curator_recommendation_id"]),
            ).fetchone()
        if row is None:
            raise PermissionError("candidate requires human approval before source intake")
        return self.records.get_human_approval(row["approval_id"])

    def record_review_event(
        self,
        *,
        candidate_id: str,
        actor: str,
        from_status: str | None,
        to_status: str,
        reason: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_status(to_status)
        event_id = event_id or prefixed_uuid("cand-evt")
        timestamp = utc_now_iso()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM candidate_sources WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if exists is None:
                raise KeyError(f"unknown candidate source: {candidate_id}")
            conn.execute(
                """
                INSERT INTO candidate_review_events (
                    event_id, candidate_id, timestamp, actor, from_status, to_status,
                    reason, notes, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    candidate_id,
                    timestamp,
                    actor,
                    from_status,
                    to_status,
                    reason,
                    notes,
                    json_dumps(metadata or {}),
                ),
            )
        return self.get_review_event(event_id)

    def get_review_event(self, event_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM candidate_review_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown candidate review event: {event_id}")
        return self._review_event_from_row(row)

    def list_review_events(self, candidate_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM candidate_review_events
                WHERE candidate_id = ?
                ORDER BY rowid
                """,
                (candidate_id,),
            ).fetchall()
        return [self._review_event_from_row(row) for row in rows]

    def _candidate_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        candidate = {
            "candidate_id": row["candidate_id"],
            "title": row["title"],
            "publisher": row["publisher"],
            "source_location": row["source_location"],
            "normalized_url": row["normalized_url"],
            "local_file_path": row["local_file_path"],
            "file_checksum": row["file_checksum"],
            "source_type": row["source_type"],
            "submitted_by": row["submitted_by"],
            "submitted_at": row["submitted_at"],
            "mission_id": row["mission_id"],
            "coverage_object_id": row["coverage_object_id"],
            "proposed_canonical_reference_type": row["proposed_canonical_reference_type"],
            "notes": row["notes"],
            "status": row["status"],
            "license_status": row["license_status"],
            "license_notes": row["license_notes"],
            "license_source_url": row["license_source_url"],
            "license_text_excerpt": row["license_text_excerpt"],
            "license_checked_at": row["license_checked_at"],
            "license_checked_by": row["license_checked_by"],
            "authority_score": row["authority_score"],
            "authority_reason": row["authority_reason"],
            "risk_notes": row["risk_notes"],
            "reviewer_notes": row["reviewer_notes"],
            "assigned_reviewer": row["assigned_reviewer"],
            "review_due_at": row["review_due_at"],
            "review_priority": row["review_priority"],
            "duplicate_of_candidate_id": row["duplicate_of_candidate_id"],
            "curator_recommendation_id": row["curator_recommendation_id"],
            "source_format": row["source_format"] if "source_format" in row.keys() else None,
            "source_authority_type": row["source_authority_type"] if "source_authority_type" in row.keys() else None,
            "publication_status": row["publication_status"] if "publication_status" in row.keys() else None,
            "metadata": json_loads(row["metadata_json"], {}),
            "updated_at": row["updated_at"],
        }
        return enrich_candidate_record(candidate)

    def _review_event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "candidate_id": row["candidate_id"],
            "timestamp": row["timestamp"],
            "actor": row["actor"],
            "from_status": row["from_status"],
            "to_status": row["to_status"],
            "reason": row["reason"],
            "notes": row["notes"],
            "metadata": json_loads(row["metadata_json"], {}),
        }

    def _validate_status(self, status: str) -> None:
        if status not in self.STATUSES:
            raise ValueError(f"invalid candidate status: {status}")


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
