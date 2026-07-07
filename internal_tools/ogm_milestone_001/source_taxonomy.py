"""Source format vs authority taxonomy helpers for intake and Curator-001."""

from __future__ import annotations

from pathlib import Path
from typing import Any

FORMAT_EXTENSIONS = {
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".webp": "image",
    ".mp4": "video",
    ".mov": "video",
    ".ppt": "slide_deck",
    ".pptx": "slide_deck",
    ".key": "slide_deck",
    ".epub": "book",
    ".mobi": "book",
}

FILE_FORMATS = frozenset({"pdf", "html", "image", "video", "slide_deck", "book", "manual", "unknown"})

TRUSTED_AUTHORITY_TYPES = frozenset(
    {
        "government",
        "government_publication",
        "university",
        "extension",
        "manufacturer",
        "professional_org",
        "professional_organization",
        "official_field_guide",
        "nonprofit",
        "public_domain_reference",
        "manufacturer_manual",
    }
)

AVOID_AUTHORITY_TYPES = frozenset(
    {
        "blog",
        "random_blog",
        "ai_generated",
        "seo_content",
        "forum",
    }
)

AUTHORITY_ALIASES = {
    "professional_organization": "professional_org",
    "government_publication": "government",
    "manufacturer_manual": "manufacturer",
    "public_domain_reference": "government",
}

NON_PUBLISHABLE_STATUSES = frozenset({"internal_only", "not_publishable"})
PACK_READY_STATUSES = frozenset({"publishable", "pack_ready"})


def infer_source_format(
    *,
    local_file_path: str | Path | None = None,
    url: str | None = None,
    explicit: str | None = None,
) -> str:
    if explicit:
        normalized = explicit.strip().lower()
        if normalized in FILE_FORMATS:
            return normalized
    if local_file_path:
        suffix = Path(str(local_file_path)).suffix.lower()
        if suffix in FORMAT_EXTENSIONS:
            fmt = FORMAT_EXTENSIONS[suffix]
            if fmt == "pdf" and "presentation" in Path(str(local_file_path)).name.lower():
                return "slide_deck"
            return fmt
    if url:
        lowered = url.lower().split("?", 1)[0]
        for suffix, fmt in FORMAT_EXTENSIONS.items():
            if lowered.endswith(suffix):
                return fmt
        if lowered.endswith("/") or "html" in lowered:
            return "html"
    return "unknown"


def infer_source_authority_type(
    *,
    source_authority_type: str | None = None,
    source_type: str | None = None,
) -> str:
    if source_authority_type:
        normalized = source_authority_type.strip().lower()
        if normalized:
            return AUTHORITY_ALIASES.get(normalized, normalized)
    if source_type:
        normalized = source_type.strip().lower()
        if normalized in FILE_FORMATS:
            return "unknown"
        return AUTHORITY_ALIASES.get(normalized, normalized)
    return "unknown"


def infer_publication_status(
    *,
    publication_status: str | None = None,
    license_status: str | None = None,
    notes: str | None = None,
    reviewer_notes: str | None = None,
) -> str:
    publication = (publication_status or "").strip().lower()
    if publication:
        return publication
    notes_text = notes or ""
    reviewer_text = reviewer_notes or ""
    if (
        "First real Tree ID source intake test" in notes_text
        or "internal Offgrid Minds Foundry workflow testing" in reviewer_text
    ):
        return "internal_only"
    if (license_status or "").strip().lower() == "internal_only":
        return "internal_only"
    return "unknown"


def normalize_candidate_taxonomy(
    *,
    source_type: str | None = None,
    source_format: str | None = None,
    source_authority_type: str | None = None,
    publication_status: str | None = None,
    license_status: str | None = None,
    local_file_path: str | Path | None = None,
    url: str | None = None,
    notes: str | None = None,
    reviewer_notes: str | None = None,
) -> dict[str, str]:
    authority = infer_source_authority_type(
        source_authority_type=source_authority_type,
        source_type=source_type,
    )
    fmt = infer_source_format(local_file_path=local_file_path, url=url, explicit=source_format)
    legacy_source_type = (source_type or "").strip().lower()
    if not legacy_source_type or legacy_source_type in FILE_FORMATS:
        legacy_source_type = authority
    publication = infer_publication_status(
        publication_status=publication_status,
        license_status=license_status,
        notes=notes,
        reviewer_notes=reviewer_notes,
    )
    return {
        "source_type": legacy_source_type,
        "source_format": fmt,
        "source_authority_type": authority,
        "publication_status": publication,
    }


def publication_warnings(publication_status: str | None, license_status: str | None = None) -> list[str]:
    warnings: list[str] = []
    status = (publication_status or "unknown").lower()
    license_value = (license_status or "unknown").lower()
    if status in NON_PUBLISHABLE_STATUSES:
        warnings.append(f"publication_status={status}; not eligible for Expert Pack compilation")
    if license_value in {"needs_review", "restricted", "rejected", "unknown"}:
        warnings.append(f"license_status={license_value}; license review incomplete or restricted")
    if status not in PACK_READY_STATUSES:
        warnings.append("source is not marked pack_ready or publishable")
    return warnings


def is_pack_ready(publication_status: str | None, license_status: str | None = None) -> bool:
    status = (publication_status or "").lower()
    license_value = (license_status or "").lower()
    return status in PACK_READY_STATUSES and license_value == "cleared"


def enrich_candidate_record(candidate: dict[str, Any]) -> dict[str, Any]:
    taxonomy = normalize_candidate_taxonomy(
        source_type=candidate.get("source_type"),
        source_format=candidate.get("source_format"),
        source_authority_type=candidate.get("source_authority_type"),
        publication_status=candidate.get("publication_status"),
        license_status=candidate.get("license_status"),
        local_file_path=candidate.get("local_file_path"),
        url=candidate.get("url") or candidate.get("source_location"),
        notes=candidate.get("notes"),
        reviewer_notes=candidate.get("reviewer_notes"),
    )
    enriched = dict(candidate)
    enriched.update(taxonomy)
    enriched["publication_warnings"] = publication_warnings(
        enriched.get("publication_status"),
        enriched.get("license_status"),
    )
    enriched["pack_ready"] = is_pack_ready(
        enriched.get("publication_status"),
        enriched.get("license_status"),
    )
    return enriched
