"""Real Foundry workspace definition for the North American Outdoor Expert Pack."""

from __future__ import annotations

from dataclasses import dataclass, field


PACK_ID = "ogm.pack.north-american-outdoor"
PACK_TITLE = "North American Outdoor Expert Pack"
WORKSPACE_ID = "foundry:north-american-outdoor:v1"
WORKSPACE_VERSION = "1.3"


@dataclass(frozen=True)
class CRSRequirementSpec:
    reference_type: str
    minimum_authority: str
    label: str


@dataclass(frozen=True)
class CoverageTopicSpec:
    slug: str
    title: str
    domain: str
    category: str
    subcategory: str
    mission_title: str
    crs_requirements: tuple[CRSRequirementSpec, ...] = field(default_factory=tuple)

    @property
    def coverage_object_id(self) -> str:
        return f"cov:{PACK_ID}:{self.category}:{self.subcategory}"

    @property
    def mission_id(self) -> str:
        return f"mission:foundry:outdoor:{self.slug}"


WORKSPACE_TOPICS: tuple[CoverageTopicSpec, ...] = (
    CoverageTopicSpec(
        slug="trees",
        title="Trees",
        domain="outdoor",
        category="species",
        subcategory="trees",
        mission_title="Build coverage for Trees",
        crs_requirements=(
            CRSRequirementSpec("government_publication", "government", "Government forestry reference"),
            CRSRequirementSpec("university_extension", "university", "University extension reference"),
            CRSRequirementSpec("professional_field_guide", "professional", "Field identification guide"),
            CRSRequirementSpec("toxic_lookalike_safety", "professional", "Toxic/lookalike safety reference"),
            CRSRequirementSpec("regional_range_map", "government", "Regional range/map reference"),
            CRSRequirementSpec("image_diagram", "professional", "Image/diagram reference"),
        ),
    ),
    CoverageTopicSpec(
        slug="mushrooms",
        title="Mushrooms",
        domain="outdoor",
        category="species",
        subcategory="mushrooms",
        mission_title="Build coverage for Mushrooms",
        crs_requirements=(
            CRSRequirementSpec("government_publication", "government", "Government mycology reference"),
            CRSRequirementSpec("university_extension", "university", "University extension reference"),
            CRSRequirementSpec("professional_field_guide", "professional", "Field identification guide"),
            CRSRequirementSpec("toxic_lookalike_safety", "professional", "Toxic/lookalike safety reference"),
            CRSRequirementSpec("regional_range_map", "government", "Regional range/map reference"),
            CRSRequirementSpec("image_diagram", "professional", "Image/diagram reference"),
        ),
    ),
    CoverageTopicSpec(
        slug="camp-stoves",
        title="Camp Stoves",
        domain="outdoor",
        category="equipment",
        subcategory="camp-stoves",
        mission_title="Build coverage for Camp Stoves",
        crs_requirements=(
            CRSRequirementSpec("manufacturer_manual", "manufacturer", "Manufacturer manual"),
            CRSRequirementSpec("safety_bulletin", "professional", "Safety bulletin"),
            CRSRequirementSpec("fuel_compatibility_reference", "manufacturer", "Fuel compatibility reference"),
            CRSRequirementSpec("maintenance_troubleshooting", "manufacturer", "Maintenance/troubleshooting reference"),
            CRSRequirementSpec("exploded_diagram_parts", "manufacturer", "Exploded diagram/parts reference"),
        ),
    ),
    CoverageTopicSpec(
        slug="water-purification",
        title="Water Purification",
        domain="outdoor",
        category="water",
        subcategory="purification",
        mission_title="Build coverage for Water Purification",
        crs_requirements=(
            CRSRequirementSpec("government_public_health", "government", "Government/public health reference"),
            CRSRequirementSpec("manufacturer_manual", "manufacturer", "Manufacturer manual"),
            CRSRequirementSpec("pathogen_removal_reference", "professional", "Pathogen/removal reference"),
            CRSRequirementSpec("field_procedure", "professional", "Field procedure reference"),
            CRSRequirementSpec("maintenance_reference", "manufacturer", "Maintenance reference"),
        ),
    ),
    CoverageTopicSpec(
        slug="weather-hazards",
        title="Weather Hazards",
        domain="outdoor",
        category="weather",
        subcategory="hazards",
        mission_title="Build coverage for Weather Hazards",
        crs_requirements=(
            CRSRequirementSpec("government_publication", "government", "Government weather reference"),
            CRSRequirementSpec("university_extension", "university", "University extension reference"),
            CRSRequirementSpec("safety_bulletin", "professional", "Safety bulletin"),
            CRSRequirementSpec("field_procedure", "professional", "Field procedure reference"),
            CRSRequirementSpec("image_diagram", "professional", "Image/diagram reference"),
        ),
    ),
    CoverageTopicSpec(
        slug="navigation-basics",
        title="Navigation Basics",
        domain="outdoor",
        category="navigation",
        subcategory="basics",
        mission_title="Build coverage for Navigation Basics",
        crs_requirements=(
            CRSRequirementSpec("government_publication", "government", "Government navigation reference"),
            CRSRequirementSpec("university_extension", "university", "University extension reference"),
            CRSRequirementSpec("professional_field_guide", "professional", "Professional field guide"),
            CRSRequirementSpec("field_procedure", "professional", "Field procedure reference"),
            CRSRequirementSpec("regional_range_map", "government", "Regional map reference"),
            CRSRequirementSpec("image_diagram", "professional", "Image/diagram reference"),
        ),
    ),
)

CANDIDATE_TEMPLATE_FIELDS: tuple[str, ...] = (
    "title",
    "publisher",
    "url",
    "local_file_path",
    "source_format",
    "source_authority_type",
    "source_type",
    "mission_id",
    "coverage_object_id",
    "proposed_canonical_reference_type",
    "submitted_by",
    "license_status",
    "publication_status",
    "license_notes",
    "authority_score",
    "authority_reason",
    "risk_notes",
    "notes",
)

CANDIDATE_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "publisher",
        "mission_id",
        "coverage_object_id",
        "proposed_canonical_reference_type",
        "submitted_by",
    }
)

