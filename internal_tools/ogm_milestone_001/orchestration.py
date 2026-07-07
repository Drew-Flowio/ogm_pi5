"""Safe orchestration helpers for approved candidate intake."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from internal_tools.ogm_milestone_001.bridge import bridge_intake_to_repository
from internal_tools.ogm_milestone_001.candidate_queue import CandidateIntakeQueue
from internal_tools.ogm_milestone_001.coverage import CoverageStore
from internal_tools.ogm_milestone_001.intake_ledger import IntakeLedger
from internal_tools.ogm_milestone_001.knowledge_repository import KnowledgeRepository
from internal_tools.ogm_milestone_001.raw_source_vault import RawSourceVault


def approved_candidate_to_repository_evidence(
    *,
    candidate_queue: CandidateIntakeQueue,
    candidate_id: str,
    ledger: IntakeLedger,
    vault: RawSourceVault,
    repository: KnowledgeRepository,
    coverage_store: CoverageStore,
    actor: str = "system",
    strict_license_review: bool = False,
    acp_log_path: str | Path | None = None,
    acp_log_store: Any | None = None,
) -> dict[str, Any]:
    """Archive an approved candidate and bridge it to repository evidence."""

    try:
        intake_payload = candidate_queue.prepare_for_vault_intake(
            candidate_id,
            strict_license_review=strict_license_review,
        )
        candidate_queue.update_candidate_review(
            candidate_id,
            status="sent_to_vault",
            actor=actor,
            reason="approved candidate sent to Raw Source Vault",
            metadata={"strict_license_review": strict_license_review},
        )

        source = vault.store_approved_source(
            intake_payload["file_path"],
            source=intake_payload["source"],
            license=intake_payload["license"],
            mission=intake_payload["mission"],
            curator=intake_payload["curator"],
            approval_status=intake_payload["approval_status"],
            metadata=intake_payload["metadata"],
            mission_id=intake_payload["mission_id"],
            coverage_object_ids=intake_payload["coverage_object_ids"],
            curator_recommendation_id=intake_payload["curator_recommendation_id"],
            human_approval_id=intake_payload["human_approval_id"],
            source_quality_score=intake_payload["source_quality_score"],
            canonical_reference_type=intake_payload["canonical_reference_type"],
            source_format=intake_payload.get("source_format"),
            source_authority_type=intake_payload.get("source_authority_type"),
            publication_status=intake_payload.get("publication_status"),
            actor=actor,
        )
        revision = source["revision"]
        candidate_queue.update_candidate_review(
            candidate_id,
            status="vaulted",
            actor=actor,
            reason="candidate archived in Raw Source Vault",
            metadata={
                "source_uuid": source["uuid"],
                "revision_uuid": revision["revision_uuid"],
            },
        )

        bridged = bridge_intake_to_repository(
            ledger=ledger,
            repository=repository,
            source_uuid=source["uuid"],
            revision_uuid=revision["revision_uuid"],
            coverage_store=coverage_store,
            vault=vault,
            actor=actor,
            acp_log_path=acp_log_path,
            acp_log_store=acp_log_store,
        )
        evidence = bridged["evidence"]
        candidate_queue.update_candidate_review(
            candidate_id,
            status="bridged_to_repository",
            actor=actor,
            reason="vaulted source bridged to repository evidence",
            metadata={
                "source_uuid": source["uuid"],
                "revision_uuid": revision["revision_uuid"],
                "evidence_uuid": evidence["evidence_uuid"],
            },
        )
        return {
            "candidate_id": candidate_id,
            "source_uuid": source["uuid"],
            "revision_uuid": revision["revision_uuid"],
            "evidence_uuid": evidence["evidence_uuid"],
            "source": source,
            "revision": revision,
            "evidence": evidence,
            "bridge": bridged,
        }
    except Exception as exc:
        candidate_queue.update_candidate_review(
            candidate_id,
            status="failed",
            actor=actor,
            reason="approved candidate intake orchestration failed",
            notes=str(exc),
            metadata={"error_type": type(exc).__name__},
        )
        raise
