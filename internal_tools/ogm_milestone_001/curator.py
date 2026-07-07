"""Curator-001 manual-first source recommendation workflow."""

from __future__ import annotations

from typing import Any

from internal_tools.ogm_milestone_001.coverage import CoverageStore
from internal_tools.ogm_milestone_001.crs_evaluation import CRSEvaluator
from internal_tools.ogm_milestone_001.records import OperationalRecords
from internal_tools.ogm_milestone_001.source_taxonomy import (
    AVOID_AUTHORITY_TYPES,
    TRUSTED_AUTHORITY_TYPES,
    infer_source_authority_type,
)
from internal_tools.ogm_milestone_001.utils import prefixed_uuid


class Curator001:
    """Narrow research librarian for North American Outdoor Pack tree coverage.

    Curator-001 does not crawl or fetch the web. It evaluates manually supplied
    candidate source records against missing CRS requirements and creates
    recommendation records for human review.
    """

    CURATOR_ID = "curator-001"
    TARGET_PACK_ID = "ogm.pack.north-american-outdoor"
    SUPPORTED_DOMAIN = "outdoor"
    SUPPORTED_SUBCATEGORY = "trees"

    TRUSTED_SOURCE_TYPES = TRUSTED_AUTHORITY_TYPES
    AVOID_SOURCE_TYPES = AVOID_AUTHORITY_TYPES
    MINIMUM_AUTHORITY_SCORE = 0.7

    def __init__(
        self,
        *,
        records: OperationalRecords,
        coverage_store: CoverageStore,
        crs_evaluator: CRSEvaluator | None = None,
    ) -> None:
        self.records = records
        self.coverage_store = coverage_store
        self.crs_evaluator = crs_evaluator or CRSEvaluator(coverage_store)

    def load_mission(self, mission_id: str) -> dict[str, Any]:
        mission = self.records.get_mission(mission_id)
        self._validate_mission_scope(mission)
        return mission

    def load_linked_coverage_objects(self, mission_id: str) -> list[dict[str, Any]]:
        mission = self.load_mission(mission_id)
        coverage_object_ids = mission["metadata"].get("coverage_object_ids", [])
        if not isinstance(coverage_object_ids, list):
            raise ValueError("mission metadata coverage_object_ids must be a list")
        coverage_objects = [
            self.coverage_store.get_coverage_object(coverage_object_id)
            for coverage_object_id in coverage_object_ids
        ]
        for coverage_object in coverage_objects:
            self._validate_coverage_scope(coverage_object)
        return coverage_objects

    def identify_missing_crs_requirements(self, mission_id: str) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for coverage_object in self.load_linked_coverage_objects(mission_id):
            score = self.crs_evaluator.score_coverage(coverage_object["coverage_object_id"])
            for requirement in score["missing_crs_requirements"]:
                missing.append(
                    {
                        "mission_id": mission_id,
                        "coverage_object": coverage_object,
                        "requirement": requirement,
                    }
                )
        return missing

    def recommend_sources(
        self,
        mission_id: str,
        *,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Evaluate manual candidates and create recommendation records."""

        self.load_mission(mission_id)
        missing = self.identify_missing_crs_requirements(mission_id)
        missing_pairs = {
            (
                item["coverage_object"]["coverage_object_id"],
                item["requirement"]["reference_type"],
            )
            for item in missing
        }

        recommendations: list[dict[str, Any]] = []
        for candidate in candidates:
            normalized = self.evaluate_candidate_source(candidate)
            pair = (
                normalized["suggested_coverage_object_id"],
                normalized["suggested_canonical_reference_type"],
            )
            if pair not in missing_pairs or normalized["decision"] != "recommend":
                continue

            recommendation = self.records.create_curator_recommendation(
                recommendation_id=normalized.get("recommendation_id") or prefixed_uuid("rec"),
                mission_id=mission_id,
                curator_id=self.CURATOR_ID,
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
                    "curator_id": self.CURATOR_ID,
                    "policy_decision": normalized["decision"],
                    "manual_candidate": True,
                    **(
                        {
                            "candidate_id": normalized["candidate_id"],
                            "queued_candidate": True,
                        }
                        if normalized.get("candidate_id")
                        else {}
                    ),
                },
            )
            recommendations.append(recommendation)
        return recommendations

    def recommend_from_queue(
        self,
        mission_id: str,
        *,
        candidate_queue: Any,
        candidate_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate queued candidates and create recommendation records."""

        self.load_mission(mission_id)
        if candidate_ids is None:
            candidates = candidate_queue.list_candidates(mission_id=mission_id, status="submitted")
        else:
            candidates = [candidate_queue.get_candidate(candidate_id) for candidate_id in candidate_ids]

        recommendations: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_queue.update_candidate_review(candidate["candidate_id"], status="under_review")
            curator_candidate = self._candidate_from_queue_record(candidate)
            normalized = self.evaluate_candidate_source(curator_candidate)
            if normalized["decision"] != "recommend":
                candidate_queue.update_candidate_review(
                    candidate["candidate_id"],
                    status="rejected",
                    reviewer_notes="Rejected by Curator-001 trusted source policy.",
                    risk_notes="; ".join(normalized["risks_limitations"]),
                )
                continue

            created = self.recommend_sources(mission_id, candidates=[curator_candidate])
            if created:
                recommendation = created[0]
                candidate_queue.update_candidate_review(
                    candidate["candidate_id"],
                    status="recommended",
                    curator_recommendation_id=recommendation["recommendation_id"],
                )
                recommendations.append(recommendation)
        return recommendations

    def evaluate_candidate_source(self, candidate: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "candidate_id": candidate.get("candidate_id"),
            "recommendation_id": candidate.get("recommendation_id"),
            "title": self._required(candidate, "title"),
            "publisher": self._required(candidate, "publisher"),
            "source_location": candidate.get("url") or candidate.get("source_location"),
            "source_type": candidate.get("source_type") or infer_source_authority_type(
                source_authority_type=candidate.get("source_authority_type"),
                source_type=candidate.get("source_type"),
            ),
            "source_format": candidate.get("source_format"),
            "source_authority_type": infer_source_authority_type(
                source_authority_type=candidate.get("source_authority_type"),
                source_type=candidate.get("source_type"),
            ),
            "publication_status": candidate.get("publication_status") or "unknown",
            "authority_score": float(candidate.get("authority_score", 0.0)),
            "license_status": self._required(candidate, "license_status"),
            "coverage_contribution": self._required(candidate, "coverage_contribution"),
            "suggested_canonical_reference_type": self._required(
                candidate, "suggested_canonical_reference_type"
            ),
            "suggested_coverage_object_id": self._required(candidate, "suggested_coverage_object_id"),
            "reason_recommended": self._required(candidate, "reason_recommended"),
            "risks_limitations": list(candidate.get("risks_limitations", [])),
        }
        if not normalized["source_location"]:
            raise ValueError("candidate requires url or source_location")
        if not 0 <= normalized["authority_score"] <= 1:
            raise ValueError("authority_score must be between 0 and 1")

        authority_type = normalized["source_authority_type"].lower()
        risks = normalized["risks_limitations"]
        if authority_type in self.AVOID_SOURCE_TYPES:
            normalized["decision"] = "reject"
            normalized["risks_limitations"] = risks + ["Authority type is excluded by Curator-001 policy."]
        elif authority_type in self.TRUSTED_SOURCE_TYPES:
            if normalized["authority_score"] < self.MINIMUM_AUTHORITY_SCORE:
                normalized["decision"] = "reject"
                normalized["risks_limitations"] = risks + ["Authority score is below Curator-001 threshold."]
            else:
                normalized["decision"] = "recommend"
        elif authority_type == "unknown":
            if normalized["authority_score"] < self.MINIMUM_AUTHORITY_SCORE:
                normalized["decision"] = "reject"
                normalized["risks_limitations"] = risks + [
                    "Authority type unknown and authority score is below Curator-001 threshold."
                ]
            else:
                normalized["decision"] = "recommend"
                normalized["risks_limitations"] = risks + [
                    "Authority type unknown; candidate allowed for human review with conservative scoring."
                ]
        else:
            normalized["decision"] = "reject"
            normalized["risks_limitations"] = risks + ["Authority type is not in the trusted source policy."]
        return normalized

    def require_human_approval_for_intake(self, recommendation_id: str) -> dict[str, Any]:
        return self.records.get_approved_recommendation_for_intake(recommendation_id)

    def _candidate_from_queue_record(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": candidate["candidate_id"],
            "recommendation_id": candidate.get("curator_recommendation_id"),
            "title": candidate["title"],
            "publisher": candidate["publisher"],
            "source_location": candidate["source_location"],
            "source_type": candidate["source_type"],
            "source_format": candidate.get("source_format"),
            "source_authority_type": candidate.get("source_authority_type"),
            "publication_status": candidate.get("publication_status"),
            "authority_score": candidate.get("authority_score") or 0.0,
            "license_status": candidate.get("license_status") or "unknown",
            "coverage_contribution": (
                f"Candidate source for {candidate['coverage_object_id']} "
                f"as {candidate['proposed_canonical_reference_type']}."
            ),
            "suggested_canonical_reference_type": candidate["proposed_canonical_reference_type"],
            "suggested_coverage_object_id": candidate["coverage_object_id"],
            "reason_recommended": candidate.get("authority_reason") or candidate.get("notes") or "Manual queue candidate.",
            "risks_limitations": [
                note
                for note in [
                    candidate.get("risk_notes"),
                    candidate.get("license_notes"),
                    candidate.get("reviewer_notes"),
                ]
                if note
            ],
        }

    def _validate_mission_scope(self, mission: dict[str, Any]) -> None:
        target_pack_id = mission.get("target_pack_id")
        if target_pack_id and target_pack_id != self.TARGET_PACK_ID:
            raise ValueError("Curator-001 only supports the North American Outdoor Expert Pack")

    def _validate_coverage_scope(self, coverage_object: dict[str, Any]) -> None:
        if coverage_object["domain"] != self.SUPPORTED_DOMAIN:
            raise ValueError("Curator-001 only supports outdoor coverage objects")
        if coverage_object["subcategory"] and coverage_object["subcategory"] != self.SUPPORTED_SUBCATEGORY:
            raise ValueError("Curator-001 only supports tree coverage objects")

    def _required(self, candidate: dict[str, Any], key: str) -> Any:
        value = candidate.get(key)
        if value in (None, ""):
            raise ValueError(f"candidate requires {key}")
        return value
