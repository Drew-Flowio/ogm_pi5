"""SQLite-backed Intake Ledger for approved source intake."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from internal_tools.ogm_milestone_001.audit import AuditLog
from internal_tools.ogm_milestone_001.schema import migrate_intake_schema
from internal_tools.ogm_milestone_001.utils import json_dumps, json_loads, prefixed_uuid, utc_now_iso


class IntakeLedger:
    """Tracks every source entering the Milestone 1 pipeline."""

    def __init__(self, db_path: str | Path, audit_log: AuditLog | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log = audit_log or AuditLog(self.db_path.with_suffix(".audit.jsonl"))
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    uuid TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    source TEXT NOT NULL,
                    license TEXT NOT NULL,
                    acquisition_date TEXT NOT NULL,
                    mission TEXT NOT NULL,
                    curator TEXT NOT NULL,
                    approval_status TEXT NOT NULL,
                    processing_state TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    current_revision_uuid TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_checksum
                ON sources(checksum);

                CREATE TABLE IF NOT EXISTS source_revisions (
                    revision_uuid TEXT PRIMARY KEY,
                    source_uuid TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    vault_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mime_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_uuid) REFERENCES sources(uuid)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )
            migrate_intake_schema(conn)

    def create_source(
        self,
        *,
        filename: str,
        checksum: str,
        source: str,
        license: str,
        mission: str,
        curator: str,
        approval_status: str,
        processing_state: str,
        mime_type: str,
        size_bytes: int,
        metadata: dict[str, Any] | None = None,
        source_uuid: str | None = None,
        acquisition_date: str | None = None,
        mission_id: str | None = None,
        coverage_object_ids: list[str] | None = None,
        curator_recommendation_id: str | None = None,
        human_approval_id: str | None = None,
        source_quality_score: float | None = None,
        canonical_reference_type: str | None = None,
        source_format: str | None = None,
        source_authority_type: str | None = None,
        publication_status: str | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        if approval_status != "approved":
            raise ValueError("Milestone 1 only accepts human-approved sources")

        now = utc_now_iso()
        source_uuid = source_uuid or prefixed_uuid("src")
        acquisition_date = acquisition_date or now
        mission_id = mission_id or mission
        metadata_json = json_dumps(metadata or {})
        coverage_object_ids_json = json_dumps(coverage_object_ids or [])

        if source_quality_score is not None and not 0 <= source_quality_score <= 1:
            raise ValueError("source_quality_score must be between 0 and 1")

        with self._connect() as conn:
            duplicate = conn.execute(
                "SELECT uuid FROM sources WHERE checksum = ?",
                (checksum,),
            ).fetchone()
            if duplicate:
                raise ValueError(f"source checksum already exists: {duplicate['uuid']}")

            conn.execute(
                """
                INSERT INTO sources (
                    uuid, filename, checksum, source, license, acquisition_date,
                    mission, curator, approval_status, processing_state, mime_type,
                    size_bytes, current_revision_uuid, metadata_json, created_at, updated_at,
                    mission_id, coverage_object_ids_json, curator_recommendation_id,
                    human_approval_id, source_quality_score, canonical_reference_type,
                    source_format, source_authority_type, publication_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_uuid,
                    filename,
                    checksum,
                    source,
                    license,
                    acquisition_date,
                    mission,
                    curator,
                    approval_status,
                    processing_state,
                    mime_type,
                    size_bytes,
                    metadata_json,
                    now,
                    now,
                    mission_id,
                    coverage_object_ids_json,
                    curator_recommendation_id,
                    human_approval_id,
                    source_quality_score,
                    canonical_reference_type,
                    source_format,
                    source_authority_type,
                    publication_status,
                ),
            )

        self.record_audit(
            action="source_created",
            entity_type="source",
            entity_id=source_uuid,
            actor=actor,
            details={
                "filename": filename,
                "checksum": checksum,
                "mission": mission,
                "mission_id": mission_id,
                "coverage_object_ids": coverage_object_ids or [],
            },
        )
        return self.get_source(source_uuid)

    def update_processing_state(
        self,
        source_uuid: str,
        processing_state: str,
        *,
        actor: str = "system",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            updated = conn.execute(
                "UPDATE sources SET processing_state = ?, updated_at = ? WHERE uuid = ?",
                (processing_state, now, source_uuid),
            ).rowcount
            if updated == 0:
                raise KeyError(f"unknown source: {source_uuid}")
        self.record_audit(
            action="source_processing_state_updated",
            entity_type="source",
            entity_id=source_uuid,
            actor=actor,
            details={"processing_state": processing_state},
        )
        return self.get_source(source_uuid)

    def add_revision(
        self,
        *,
        source_uuid: str,
        filename: str,
        checksum: str,
        vault_path: str,
        size_bytes: int,
        mime_type: str,
        metadata: dict[str, Any] | None = None,
        revision_uuid: str | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        revision_uuid = revision_uuid or prefixed_uuid("rev")
        now = utc_now_iso()
        metadata_json = json_dumps(metadata or {})

        with self._connect() as conn:
            current = conn.execute(
                "SELECT COALESCE(MAX(revision_number), 0) AS n FROM source_revisions WHERE source_uuid = ?",
                (source_uuid,),
            ).fetchone()
            revision_number = int(current["n"]) + 1
            conn.execute(
                """
                INSERT INTO source_revisions (
                    revision_uuid, source_uuid, revision_number, filename, checksum,
                    vault_path, size_bytes, mime_type, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_uuid,
                    source_uuid,
                    revision_number,
                    filename,
                    checksum,
                    vault_path,
                    size_bytes,
                    mime_type,
                    metadata_json,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE sources
                SET current_revision_uuid = ?, updated_at = ?, processing_state = ?
                WHERE uuid = ?
                """,
                (revision_uuid, now, "raw_archived", source_uuid),
            )

        self.record_audit(
            action="source_revision_created",
            entity_type="source_revision",
            entity_id=revision_uuid,
            actor=actor,
            details={"source_uuid": source_uuid, "revision_number": revision_number},
        )
        return self.get_revision(revision_uuid)

    def record_audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = self.audit_log.append(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            details=details or {},
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (
                    audit_id, timestamp, actor, action, entity_type, entity_id, details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["audit_id"],
                    event["timestamp"],
                    event["actor"],
                    event["action"],
                    event["entity_type"],
                    event["entity_id"],
                    json_dumps(event["details"]),
                ),
            )
        return event

    def get_source(self, source_uuid: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE uuid = ?", (source_uuid,)).fetchone()
        if row is None:
            raise KeyError(f"unknown source: {source_uuid}")
        return self._source_from_row(row)

    def find_source_by_checksum(self, checksum: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE checksum = ?", (checksum,)).fetchone()
        return self._source_from_row(row) if row else None

    def list_sources(
        self,
        *,
        mission: str | None = None,
        mission_id: str | None = None,
        processing_state: str | None = None,
        approval_status: str | None = None,
        license: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for field, value in (
            ("mission", mission),
            ("mission_id", mission_id),
            ("processing_state", processing_state),
            ("approval_status", approval_status),
            ("license", license),
        ):
            if value is not None:
                clauses.append(f"{field} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM sources {where} ORDER BY created_at", params).fetchall()
        return [self._source_from_row(row) for row in rows]

    def get_revision(self, revision_uuid: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_revisions WHERE revision_uuid = ?",
                (revision_uuid,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown source revision: {revision_uuid}")
        return self._revision_from_row(row)

    def list_revisions(self, source_uuid: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM source_revisions WHERE source_uuid = ? ORDER BY revision_number",
                (source_uuid,),
            ).fetchall()
        return [self._revision_from_row(row) for row in rows]

    def list_audit_events(self, entity_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM audit_events"
        params: tuple[Any, ...] = ()
        if entity_id is not None:
            query += " WHERE entity_id = ?"
            params = (entity_id,)
        query += " ORDER BY timestamp"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "audit_id": row["audit_id"],
                "timestamp": row["timestamp"],
                "actor": row["actor"],
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "details": json_loads(row["details_json"], {}),
            }
            for row in rows
        ]

    def _source_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json_loads(data.pop("metadata_json"), {})
        coverage_raw = data.pop("coverage_object_ids_json", "[]")
        data["coverage_object_ids"] = json_loads(coverage_raw, [])
        if not data.get("mission_id"):
            data["mission_id"] = data.get("mission")
        return data

    def _revision_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json_loads(data.pop("metadata_json"), {})
        return data
