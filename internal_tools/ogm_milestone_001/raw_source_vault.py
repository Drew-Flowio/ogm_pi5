"""Immutable Raw Source Vault."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from internal_tools.ogm_milestone_001.intake_ledger import IntakeLedger
from internal_tools.ogm_milestone_001.utils import (
    detect_mime_type,
    ensure_relative_name,
    prefixed_uuid,
    sha256_file,
    utc_now_iso,
)


class RawSourceVault:
    """Archives approved source files without overwriting originals."""

    def __init__(self, vault_root: str | Path, ledger: IntakeLedger) -> None:
        self.vault_root = Path(vault_root)
        self.ledger = ledger
        self.vault_root.mkdir(parents=True, exist_ok=True)

    def store_approved_source(
        self,
        file_path: str | Path,
        *,
        source: str,
        license: str,
        mission: str,
        curator: str,
        approval_status: str,
        metadata: dict[str, Any] | None = None,
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
        """Store an approved source file and create ledger records.

        Milestone 1 accepts only approved sources. The file is copied into a
        source UUID and revision UUID directory. Existing archived files are
        never overwritten.
        """

        if approval_status != "approved":
            raise ValueError("Raw Source Vault only stores human-approved sources")

        source_file = Path(file_path)
        if not source_file.is_file():
            raise FileNotFoundError(source_file)

        checksum = sha256_file(source_file)
        duplicate = self.ledger.find_source_by_checksum(checksum)
        if duplicate is not None:
            raise ValueError(f"source checksum already archived: {duplicate['uuid']}")

        filename = ensure_relative_name(source_file.name)
        size_bytes = source_file.stat().st_size
        mime_type = detect_mime_type(source_file)
        now = utc_now_iso()
        source_uuid = prefixed_uuid("src")
        revision_uuid = prefixed_uuid("rev")

        revision_dir = self.vault_root / source_uuid / revision_uuid
        revision_dir.mkdir(parents=True, exist_ok=False)
        target_path = revision_dir / filename
        if target_path.exists():
            raise FileExistsError(target_path)

        temp_path = revision_dir / f".{filename}.tmp"
        shutil.copy2(source_file, temp_path)
        copied_checksum = sha256_file(temp_path)
        if copied_checksum != checksum:
            temp_path.unlink(missing_ok=True)
            raise ValueError("copied file checksum did not match source checksum")
        temp_path.rename(target_path)
        target_path.chmod(0o444)

        combined_metadata = {
            "original_path": str(source_file),
            "vaulted_at": now,
            **(metadata or {}),
        }
        source_record = self.ledger.create_source(
            source_uuid=source_uuid,
            filename=filename,
            checksum=checksum,
            source=source,
            license=license,
            mission=mission,
            curator=curator,
            approval_status=approval_status,
            processing_state="raw_archived",
            mime_type=mime_type,
            size_bytes=size_bytes,
            metadata=combined_metadata,
            acquisition_date=now,
            mission_id=mission_id or mission,
            coverage_object_ids=coverage_object_ids,
            curator_recommendation_id=curator_recommendation_id,
            human_approval_id=human_approval_id,
            source_quality_score=source_quality_score,
            canonical_reference_type=canonical_reference_type,
            source_format=source_format,
            source_authority_type=source_authority_type,
            publication_status=publication_status,
            actor=actor,
        )
        revision_record = self.ledger.add_revision(
            revision_uuid=revision_uuid,
            source_uuid=source_uuid,
            filename=filename,
            checksum=checksum,
            vault_path=str(target_path),
            size_bytes=size_bytes,
            mime_type=mime_type,
            metadata=combined_metadata,
            actor=actor,
        )
        self.ledger.record_audit(
            action="raw_source_archived",
            entity_type="source",
            entity_id=source_uuid,
            actor=actor,
            details={
                "revision_uuid": revision_uuid,
                "vault_path": str(target_path),
                "checksum": checksum,
            },
        )
        source_record["revision"] = revision_record
        return source_record

    def verify_revision(self, revision_uuid: str) -> bool:
        revision = self.ledger.get_revision(revision_uuid)
        vault_path = Path(revision["vault_path"])
        if not vault_path.is_file():
            return False
        return sha256_file(vault_path) == revision["checksum"]
