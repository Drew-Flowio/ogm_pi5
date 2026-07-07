"""Curator evaluation workflow for Foundry CLI commands."""

from __future__ import annotations

from typing import Any

from internal_tools.ogm_foundry.runtime import FoundryServices
from internal_tools.ogm_milestone_001.utils import prefixed_uuid


def list_candidates_for_evaluation(
    services: FoundryServices,
    *,
    mission_id: str | None = None,
    coverage_object_id: str | None = None,
    candidate_id: str | None = None,
) -> list[dict[str, Any]]:
    if candidate_id is not None:
        candidate = services.queue.get_candidate(candidate_id)
        if candidate["status"] != "submitted":
            raise ValueError(f"candidate must be submitted for evaluation: {candidate_id}")
        return [candidate]

    candidates = services.queue.list_candidates(status="submitted")
    if mission_id is not None:
        candidates = [item for item in candidates if item["mission_id"] == mission_id]
    if coverage_object_id is not None:
        candidates = [item for item in candidates if item["coverage_object_id"] == coverage_object_id]
    return candidates


def evaluate_candidates(
    services: FoundryServices,
    *,
    mission_id: str | None = None,
    coverage_object_id: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    candidates = list_candidates_for_evaluation(
        services,
        mission_id=mission_id,
        coverage_object_id=coverage_object_id,
        candidate_id=candidate_id,
    )
    if not candidates:
        return {
            "evaluated": 0,
            "recommended": [],
            "rejected": [],
            "skipped": [],
            "message": "No submitted candidates matched the filters.",
        }

    recommended: list[str] = []
    rejected: list[str] = []
    skipped: list[str] = []

    for candidate in candidates:
        services.records.get_mission(candidate["mission_id"])
        services.queue.update_candidate_review(
            candidate["candidate_id"],
            status="under_review",
            actor=services.curator.CURATOR_ID,
            reason="Curator-001 evaluation started",
        )
        curator_candidate = services.curator._candidate_from_queue_record(candidate)
        normalized = services.curator.evaluate_candidate_source(curator_candidate)
        if normalized["decision"] != "recommend":
            services.queue.update_candidate_review(
                candidate["candidate_id"],
                status="rejected",
                actor=services.curator.CURATOR_ID,
                reason="Rejected by Curator-001 trusted source policy",
                reviewer_notes="Rejected by Curator-001 trusted source policy.",
                risk_notes="; ".join(normalized["risks_limitations"]),
            )
            rejected.append(candidate["candidate_id"])
            continue

        score = services.crs_evaluator.score_coverage(candidate["coverage_object_id"])
        missing_types = {req["reference_type"] for req in score["missing_crs_requirements"]}
        proposed_type = candidate["proposed_canonical_reference_type"]
        if proposed_type not in missing_types:
            services.queue.update_candidate_review(
                candidate["candidate_id"],
                status="rejected",
                actor=services.curator.CURATOR_ID,
                reason="Candidate CRS type is not currently missing for coverage object",
                reviewer_notes=f"Proposed CRS type '{proposed_type}' is not missing.",
            )
            skipped.append(candidate["candidate_id"])
            continue

        recommendation = services.records.create_curator_recommendation(
            recommendation_id=normalized.get("recommendation_id") or prefixed_uuid("rec"),
            mission_id=candidate["mission_id"],
            curator_id=services.curator.CURATOR_ID,
            source_label=normalized["title"],
            status="submitted",
            title=normalized["title"],
            publisher=normalized["publisher"],
            source_location=normalized["source_location"],
            source_type=normalized["source_type"],
            authority_score=normalized["authority_score"],
            license_status=normalized["license_status"],
            coverage_contribution=normalized["coverage_contribution"],
            suggested_canonical_reference_type=normalized["suggested_canonical_reference_type"],
            suggested_coverage_object_id=normalized["suggested_coverage_object_id"],
            reason_recommended=normalized["reason_recommended"],
            risks_limitations=normalized["risks_limitations"],
                metadata={
                    "curator_id": services.curator.CURATOR_ID,
                    "policy_decision": normalized["decision"],
                    "queued_candidate": True,
                    "candidate_id": candidate["candidate_id"],
                    "source_format": normalized.get("source_format"),
                    "source_authority_type": normalized.get("source_authority_type"),
                    "publication_status": normalized.get("publication_status"),
                },
        )
        services.queue.update_candidate_review(
            candidate["candidate_id"],
            status="recommended",
            actor=services.curator.CURATOR_ID,
            reason="Curator-001 created recommendation",
            curator_recommendation_id=recommendation["recommendation_id"],
        )
        recommended.append(candidate["candidate_id"])

    return {
        "evaluated": len(candidates),
        "recommended": recommended,
        "rejected": rejected,
        "skipped": skipped,
        "message": None,
    }
