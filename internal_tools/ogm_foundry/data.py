"""Read-only data access for Foundry Dashboard v1."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from internal_tools.ogm_foundry.config import FoundryConfig
from internal_tools.ogm_milestone_001.candidate_queue import CandidateIntakeQueue
from internal_tools.ogm_milestone_001.coverage import CoverageStore
from internal_tools.ogm_milestone_001.crs_evaluation import CRSEvaluator
from internal_tools.ogm_milestone_001.curator import Curator001
from internal_tools.ogm_milestone_001.intake_ledger import IntakeLedger
from internal_tools.ogm_milestone_001.knowledge_repository import KnowledgeRepository
from internal_tools.ogm_milestone_001.records import OperationalRecords


@dataclass
class BackendAvailability:
    intake_db: bool
    repository_db: bool
    vault_root: bool
    intake_db_path: str
    repository_db_path: str
    vault_root_path: str


class FoundryDataReader:
    """Aggregates read-only metrics from Milestone 1–6 backend stores."""

    def __init__(self, config: FoundryConfig | None = None) -> None:
        self.config = config or FoundryConfig.from_env()
        self._started_at = datetime.now(timezone.utc)

    def availability(self) -> BackendAvailability:
        return BackendAvailability(
            intake_db=self.config.intake_db.is_file(),
            repository_db=self.config.repository_db.is_file(),
            vault_root=self.config.vault_root.is_dir(),
            intake_db_path=str(self.config.intake_db),
            repository_db_path=str(self.config.repository_db),
            vault_root_path=str(self.config.vault_root),
        )

    def health(self) -> dict[str, Any]:
        availability = self.availability()
        issues: list[str] = []
        if not availability.intake_db:
            issues.append("Intake database not found.")
        if not availability.repository_db:
            issues.append("Repository database not found.")
        if not availability.vault_root:
            issues.append("Vault directory not found.")

        return {
            "status": "ok" if not issues else "degraded",
            "uptime_seconds": int((datetime.now(timezone.utc) - self._started_at).total_seconds()),
            "backend": {
                "intake_db": availability.intake_db,
                "repository_db": availability.repository_db,
                "vault_root": availability.vault_root,
            },
            "paths": {
                "intake_db": availability.intake_db_path,
                "repository_db": availability.repository_db_path,
                "vault_root": availability.vault_root_path,
            },
            "issues": issues,
            "capabilities": {
                "ocr": False,
                "embeddings": False,
                "pack_compilation": False,
                "autonomous_crawling": False,
                "login_auth": False,
            },
        }

    def dashboard_summary(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "health": self.health(),
            "repository": self.repository_counts(),
            "coverage": self.coverage_summary(),
            "crs_requirements": self.coverage_requirements(),
            "missions": self.missions_summary(),
            "candidate_queue": self.candidate_counts(),
            "candidates": self.candidates(),
            "vault": self.vault_counts(),
            "curator": self.curator_status(),
            "recent_events": self.recent_events(limit=12),
        }

    def missions(self) -> dict[str, Any]:
        missions = self._safe_list_missions()
        return {"items": missions, "count": len(missions)}

    def coverage_objects(self) -> dict[str, Any]:
        items = self._safe_list_coverage_objects()
        return {"items": items, "count": len(items)}

    def coverage_requirements(self) -> dict[str, Any]:
        if not self.availability().repository_db:
            return {
                "total_requirements": 0,
                "items": [],
                "placeholder": True,
                "message": "Repository database not configured.",
            }
        try:
            coverage = CoverageStore(self.config.repository_db)
            evaluator = None
            if self.availability().intake_db:
                try:
                    evaluator = CRSEvaluator(
                        coverage,
                        ledger=IntakeLedger(self.config.intake_db),
                        repository=KnowledgeRepository(self.config.repository_db),
                    )
                except sqlite3.Error:
                    evaluator = None
            items: list[dict[str, Any]] = []
            total_requirements = 0
            for coverage_object in coverage.list_coverage_objects():
                requirements = coverage.list_canonical_reference_requirements(
                    coverage_object["coverage_object_id"]
                )
                missing_requirements = []
                if evaluator is not None:
                    score = evaluator.score_coverage(coverage_object["coverage_object_id"])
                    missing_requirements = [
                        {
                            "reference_type": req["reference_type"],
                            "minimum_authority": req.get("minimum_authority"),
                            "label": req.get("metadata", {}).get("label"),
                        }
                        for req in score["missing_crs_requirements"]
                    ]
                total_requirements += len(requirements)
                items.append(
                    {
                        "coverage_object_id": coverage_object["coverage_object_id"],
                        "title": coverage_object["title"],
                        "status": coverage_object["status"],
                        "coverage_percentage": coverage_object["coverage_percentage"],
                        "required_crs_count": len(requirements),
                        "missing_crs_count": len(missing_requirements),
                        "missing_crs_requirements": missing_requirements,
                        "requirements": [
                            {
                                "requirement_id": req["requirement_id"],
                                "reference_type": req["reference_type"],
                                "minimum_authority": req["minimum_authority"],
                                "label": req.get("metadata", {}).get("label"),
                            }
                            for req in requirements
                        ],
                    }
                )
            return {
                "total_requirements": total_requirements,
                "items": items,
                "placeholder": total_requirements == 0,
                "message": None if total_requirements else "No CRS requirements configured yet.",
            }
        except sqlite3.Error as exc:
            return {
                "total_requirements": 0,
                "items": [],
                "placeholder": True,
                "message": f"Unable to read CRS requirements: {exc}",
            }

    def candidate_counts(self) -> dict[str, Any]:
        availability = self.availability()
        if not availability.intake_db:
            return self._empty_candidate_counts("Intake database not configured.")

        counts = {status: 0 for status in CandidateIntakeQueue.STATUSES}
        duplicates = 0
        try:
            queue = CandidateIntakeQueue(self.config.intake_db)
            for candidate in queue.list_candidates():
                counts[candidate["status"]] = counts.get(candidate["status"], 0) + 1
                if candidate.get("duplicate_of_candidate_id"):
                    duplicates += 1
        except sqlite3.Error as exc:
            return self._empty_candidate_counts(f"Unable to read candidate queue: {exc}")

        total = sum(counts.values())
        return {
            "total": total,
            "by_status": counts,
            "duplicates": duplicates,
            "pending_review": counts.get("submitted", 0) + counts.get("under_review", 0),
            "recommended": counts.get("recommended", 0),
            "approved_for_intake": counts.get("approved_for_intake", 0),
            "awaiting_vault_intake": counts.get("approved_for_intake", 0),
            "rejected": counts.get("rejected", 0),
            "vaulted_or_beyond": (
                counts.get("sent_to_vault", 0)
                + counts.get("vaulted", 0)
                + counts.get("bridged_to_repository", 0)
            ),
            "placeholder": False,
            "message": None if total else "No candidate sources submitted yet.",
        }

    def candidates(self, *, limit: int = 20) -> dict[str, Any]:
        availability = self.availability()
        if not availability.intake_db:
            return {"items": [], "count": 0, "placeholder": True, "message": "Intake database not configured."}
        try:
            queue = CandidateIntakeQueue(self.config.intake_db)
            rows = queue.list_candidates()
            items = [
                {
                    "candidate_id": row["candidate_id"],
                    "title": row["title"],
                    "publisher": row["publisher"],
                    "status": row["status"],
                    "mission_id": row["mission_id"],
                    "coverage_object_id": row["coverage_object_id"],
                    "proposed_canonical_reference_type": row["proposed_canonical_reference_type"],
                    "source_format": row.get("source_format"),
                    "source_authority_type": row.get("source_authority_type"),
                    "source_type": row.get("source_type"),
                    "license_status": row.get("license_status"),
                    "publication_status": row.get("publication_status"),
                    "pack_ready": row.get("pack_ready", False),
                    "publication_warnings": row.get("publication_warnings") or [],
                    "curator_recommendation_id": row.get("curator_recommendation_id"),
                    "submitted_at": row["submitted_at"],
                    "has_local_file": bool(row.get("local_file_path")),
                }
                for row in rows[:limit]
            ]
            return {
                "items": items,
                "count": len(rows),
                "placeholder": len(rows) == 0,
                "message": None if rows else "No candidate sources submitted yet.",
            }
        except sqlite3.Error as exc:
            return {
                "items": [],
                "count": 0,
                "placeholder": True,
                "message": f"Unable to read candidates: {exc}",
            }

    def repository_counts(self) -> dict[str, Any]:
        availability = self.availability()
        if not availability.repository_db:
            return {
                "knowledge_objects": 0,
                "evidence": 0,
                "relationships": 0,
                "coverage_objects": 0,
                "by_status": {},
                "by_category": {},
                "placeholder": True,
                "message": "Repository database not configured.",
            }

        try:
            repository = KnowledgeRepository(self.config.repository_db)
            coverage = CoverageStore(self.config.repository_db)
            objects = repository.list_objects()
            evidence = repository.list_evidence()
            relationships = repository.list_relationships()
            coverage_objects = coverage.list_coverage_objects()

            by_status: dict[str, int] = {}
            by_category: dict[str, int] = {}
            for obj in objects:
                by_status[obj["status"]] = by_status.get(obj["status"], 0) + 1
                by_category[obj["category"]] = by_category.get(obj["category"], 0) + 1

            return {
                "knowledge_objects": len(objects),
                "evidence": len(evidence),
                "relationships": len(relationships),
                "coverage_objects": len(coverage_objects),
                "by_status": by_status,
                "by_category": by_category,
                "placeholder": False,
                "message": None if objects else "Repository initialized; no knowledge objects yet.",
            }
        except sqlite3.Error as exc:
            return {
                "knowledge_objects": 0,
                "evidence": 0,
                "relationships": 0,
                "coverage_objects": 0,
                "by_status": {},
                "by_category": {},
                "placeholder": True,
                "message": f"Unable to read repository database: {exc}",
            }

    def vault_counts(self) -> dict[str, Any]:
        availability = self.availability()
        sources = 0
        revisions = 0
        archived_bytes = 0
        message = None
        placeholder = False

        if availability.intake_db:
            try:
                ledger = IntakeLedger(self.config.intake_db)
                source_rows = ledger.list_sources()
                sources = len(source_rows)
                for source in source_rows:
                    revisions += len(ledger.list_revisions(source["uuid"]))
            except sqlite3.Error as exc:
                message = f"Unable to read intake ledger: {exc}"
                placeholder = True
                source_rows = []
        else:
            message = "Intake database not configured."
            placeholder = True
            source_rows = []

        if availability.vault_root:
            for path in self.config.vault_root.rglob("*"):
                if path.is_file() and not path.name.startswith("."):
                    archived_bytes += path.stat().st_size
        elif message is None:
            message = "Vault directory not configured."
            placeholder = True

        return {
            "sources": sources,
            "revisions": revisions,
            "archived_bytes": archived_bytes,
            "items": [
                {
                    "source_uuid": source.get("uuid"),
                    "filename": source.get("filename"),
                    "source_format": source.get("source_format") or source.get("metadata", {}).get("source_format"),
                    "source_authority_type": source.get("source_authority_type")
                    or source.get("metadata", {}).get("source_authority_type"),
                    "license_status": source.get("license"),
                    "publication_status": source.get("publication_status")
                    or source.get("metadata", {}).get("publication_status"),
                    "canonical_reference_type": source.get("canonical_reference_type"),
                    "pack_ready": source.get("metadata", {}).get("pack_ready", False),
                }
                for source in source_rows
            ],
            "placeholder": placeholder,
            "message": message if sources == 0 else None,
        }

    def curator_status(self) -> dict[str, Any]:
        availability = self.availability()
        if not availability.intake_db:
            return {
                "agent_id": Curator001.CURATOR_ID,
                "scope": "North American Outdoor Expert Pack → Trees",
                "recommendations_total": 0,
                "recommendations_submitted": 0,
                "approvals_total": 0,
                "approvals_approved": 0,
                "mode": "manual-first",
                "placeholder": True,
                "message": "Operational records database not configured.",
            }

        try:
            records = OperationalRecords(self.config.intake_db)
            recommendations = records.list_curator_recommendations()
            approvals = records.list_human_approvals()
            submitted = [rec for rec in recommendations if rec["status"] == "submitted"]
            approved = [item for item in approvals if item["decision"] == "approved"]
            return {
                "agent_id": Curator001.CURATOR_ID,
                "scope": "North American Outdoor Expert Pack → Trees",
                "recommendations_total": len(recommendations),
                "recommendations_submitted": len(submitted),
                "approvals_total": len(approvals),
                "approvals_approved": len(approved),
                "mode": "manual-first",
                "placeholder": False,
                "message": None if recommendations else "Curator-001 idle; no recommendations recorded yet.",
            }
        except sqlite3.Error as exc:
            return {
                "agent_id": Curator001.CURATOR_ID,
                "scope": "North American Outdoor Expert Pack → Trees",
                "recommendations_total": 0,
                "recommendations_submitted": 0,
                "approvals_total": 0,
                "approvals_approved": 0,
                "mode": "manual-first",
                "placeholder": True,
                "message": f"Unable to read curator records: {exc}",
            }

    def recent_events(self, *, limit: int = 20) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        availability = self.availability()

        if availability.intake_db:
            events.extend(self._sqlite_audit_events(self.config.intake_db, source="intake"))
            events.extend(self._candidate_review_events(limit=limit))

        if availability.repository_db:
            events.extend(self._sqlite_audit_events(self.config.repository_db, source="repository"))
            events.extend(self._jsonl_audit_events(self.config.repository_db.with_suffix(".audit.jsonl"), source="repository_log"))

        if availability.intake_db:
            events.extend(self._jsonl_audit_events(self.config.intake_db.with_suffix(".audit.jsonl"), source="intake_log"))

        events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        trimmed = events[:limit]
        return {
            "items": trimmed,
            "count": len(trimmed),
            "placeholder": len(trimmed) == 0,
            "message": None if trimmed else "No audit or review events recorded yet.",
        }

    def coverage_summary(self) -> dict[str, Any]:
        items = self._safe_list_coverage_objects()
        if not items:
            return {
                "total": 0,
                "complete": 0,
                "partial": 0,
                "not_started": 0,
                "average_coverage_percentage": 0.0,
                "items": [],
                "placeholder": True,
                "message": "No coverage objects configured yet.",
            }

        complete = sum(1 for item in items if item["status"] == "complete")
        partial = sum(1 for item in items if item["status"] == "partial")
        not_started = sum(1 for item in items if item["status"] == "not_started")
        average = round(sum(item["coverage_percentage"] for item in items) / len(items), 4)
        preview = []
        coverage_store = CoverageStore(self.config.repository_db) if self.availability().repository_db else None
        for item in items[:8]:
            crs_count = 0
            if coverage_store is not None:
                try:
                    crs_count = len(
                        coverage_store.list_canonical_reference_requirements(item["coverage_object_id"])
                    )
                except sqlite3.Error:
                    crs_count = 0
            preview.append({**item, "required_crs_count": crs_count})
        return {
            "total": len(items),
            "complete": complete,
            "partial": partial,
            "not_started": not_started,
            "average_coverage_percentage": average,
            "items": preview,
            "placeholder": False,
            "message": None if average > 0 else "Coverage initialized; awaiting approved sources.",
        }

    def missions_summary(self) -> dict[str, Any]:
        missions = self._safe_list_missions()
        active = [mission for mission in missions if mission["status"] == "active"]
        return {
            "total": len(missions),
            "active": len(active),
            "items": missions[:8],
            "placeholder": len(missions) == 0,
            "message": None if missions else "No missions recorded yet.",
        }

    def _safe_list_missions(self) -> list[dict[str, Any]]:
        if not self.availability().intake_db:
            return []
        try:
            return OperationalRecords(self.config.intake_db).list_missions()
        except sqlite3.Error:
            return []

    def _safe_list_coverage_objects(self) -> list[dict[str, Any]]:
        if not self.availability().repository_db:
            return []
        try:
            return CoverageStore(self.config.repository_db).list_coverage_objects()
        except sqlite3.Error:
            return []

    def _empty_candidate_counts(self, message: str) -> dict[str, Any]:
        return {
            "total": 0,
            "by_status": {},
            "duplicates": 0,
            "pending_review": 0,
            "recommended": 0,
            "approved_for_intake": 0,
            "awaiting_vault_intake": 0,
            "rejected": 0,
            "vaulted_or_beyond": 0,
            "placeholder": True,
            "message": message,
        }

    def _sqlite_audit_events(self, db_path: Path, *, source: str) -> list[dict[str, Any]]:
        if not db_path.is_file():
            return []
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT audit_id, timestamp, actor, action, entity_type, entity_id, details_json
                    FROM audit_events
                    ORDER BY timestamp DESC
                    LIMIT 50
                    """
                ).fetchall()
        except sqlite3.Error:
            return []

        events: list[dict[str, Any]] = []
        for row in rows:
            details = {}
            try:
                details = json.loads(row["details_json"] or "{}")
            except json.JSONDecodeError:
                details = {"raw": row["details_json"]}
            events.append(
                {
                    "event_id": row["audit_id"],
                    "timestamp": row["timestamp"],
                    "actor": row["actor"],
                    "action": row["action"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "details": details,
                    "source": source,
                }
            )
        return events

    def _candidate_review_events(self, *, limit: int) -> list[dict[str, Any]]:
        if not self.config.intake_db.is_file():
            return []
        try:
            with sqlite3.connect(self.config.intake_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT event_id, candidate_id, timestamp, actor, from_status, to_status, reason, notes
                    FROM candidate_review_events
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        except sqlite3.Error:
            return []

        return [
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "actor": row["actor"],
                "action": f"candidate_{row['to_status']}",
                "entity_type": "candidate_source",
                "entity_id": row["candidate_id"],
                "details": {
                    "from_status": row["from_status"],
                    "to_status": row["to_status"],
                    "reason": row["reason"],
                    "notes": row["notes"],
                },
                "source": "candidate_review",
            }
            for row in rows
        ]

    def _jsonl_audit_events(self, path: Path, *, source: str) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    events.append(
                        {
                            "event_id": payload.get("audit_id", payload.get("id", "unknown")),
                            "timestamp": payload.get("timestamp", ""),
                            "actor": payload.get("actor", "system"),
                            "action": payload.get("action", "audit"),
                            "entity_type": payload.get("entity_type", "unknown"),
                            "entity_id": payload.get("entity_id", ""),
                            "details": payload.get("details", {}),
                            "source": source,
                        }
                    )
        except (OSError, json.JSONDecodeError):
            return []
        return events[-50:]
