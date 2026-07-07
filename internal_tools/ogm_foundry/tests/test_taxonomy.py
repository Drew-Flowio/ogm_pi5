import sqlite3
import tempfile
import unittest
from pathlib import Path

from internal_tools.ogm_foundry.bootstrap_workspace import bootstrap_workspace
from internal_tools.ogm_foundry.config import FoundryConfig
from internal_tools.ogm_foundry.data import FoundryDataReader
from internal_tools.ogm_foundry.import_candidates import import_candidates, parse_candidate_row
from internal_tools.ogm_milestone_001.candidate_queue import CandidateIntakeQueue
from internal_tools.ogm_milestone_001.curator import Curator001
from internal_tools.ogm_milestone_001.intake_ledger import IntakeLedger
from internal_tools.ogm_milestone_001.records import OperationalRecords
from internal_tools.ogm_milestone_001.source_taxonomy import (
    infer_source_format,
    is_pack_ready,
    normalize_candidate_taxonomy,
)


class SourceTaxonomyTests(unittest.TestCase):
    def test_pdf_is_accepted_as_source_format(self):
        self.assertEqual(
            infer_source_format(local_file_path="/tmp/reference.pdf"),
            "pdf",
        )
        taxonomy = normalize_candidate_taxonomy(
            source_format="pdf",
            source_authority_type="government",
            source_type="pdf",
        )
        self.assertEqual(taxonomy["source_format"], "pdf")
        self.assertEqual(taxonomy["source_authority_type"], "government")

    def test_authority_evaluation_uses_source_authority_type(self):
        curator = Curator001(records=OperationalRecords(":memory:"), coverage_store=_FakeCoverage())
        result = curator.evaluate_candidate_source(
            {
                "title": "USFS Guide",
                "publisher": "USFS",
                "source_location": "/tmp/guide.pdf",
                "source_format": "pdf",
                "source_authority_type": "government",
                "source_type": "pdf",
                "authority_score": 0.9,
                "license_status": "needs_review",
                "coverage_contribution": "Trees CRS",
                "suggested_canonical_reference_type": "government_publication",
                "suggested_coverage_object_id": "cov:trees",
                "reason_recommended": "Government forestry reference",
            }
        )
        self.assertEqual(result["decision"], "recommend")

    def test_unknown_authority_is_allowed_with_conservative_risks(self):
        curator = Curator001(records=OperationalRecords(":memory:"), coverage_store=_FakeCoverage())
        result = curator.evaluate_candidate_source(
            {
                "title": "Unknown PDF",
                "publisher": "Unknown",
                "source_location": "/tmp/unknown.pdf",
                "source_format": "pdf",
                "source_authority_type": "unknown",
                "source_type": "pdf",
                "authority_score": 0.72,
                "license_status": "needs_review",
                "coverage_contribution": "Trees CRS",
                "suggested_canonical_reference_type": "image_diagram",
                "suggested_coverage_object_id": "cov:trees",
                "reason_recommended": "Needs review",
            }
        )
        self.assertEqual(result["decision"], "recommend")
        self.assertTrue(any("unknown" in note.lower() for note in result["risks_limitations"]))

    def test_csv_import_supports_new_fields(self):
        row = parse_candidate_row(
            {
                "title": "Guide",
                "publisher": "USFS",
                "url": "",
                "local_file_path": "/tmp/guide.pdf",
                "source_format": "pdf",
                "source_authority_type": "government",
                "source_type": "",
                "mission_id": "mission:foundry:outdoor:trees",
                "coverage_object_id": "cov:ogm.pack.north-american-outdoor:species:trees",
                "proposed_canonical_reference_type": "government_publication",
                "submitted_by": "Andrew",
                "license_status": "needs_review",
                "publication_status": "internal_only",
                "license_notes": "",
                "authority_score": "0.9",
                "authority_reason": "Government source",
                "risk_notes": "",
                "notes": "",
            },
            row_number=2,
        )
        self.assertEqual(row["source_format"], "pdf")
        self.assertEqual(row["source_authority_type"], "government")
        self.assertEqual(row["publication_status"], "internal_only")

    def test_old_csv_format_remains_backward_compatible(self):
        row = parse_candidate_row(
            {
                "title": "Guide",
                "publisher": "USFS",
                "url": "",
                "local_file_path": "/tmp/guide.pdf",
                "source_type": "government",
                "mission_id": "mission:foundry:outdoor:trees",
                "coverage_object_id": "cov:ogm.pack.north-american-outdoor:species:trees",
                "proposed_canonical_reference_type": "government_publication",
                "submitted_by": "Andrew",
                "license_status": "needs_review",
                "license_notes": "",
                "authority_score": "0.9",
                "authority_reason": "Government source",
                "risk_notes": "",
                "notes": "",
            },
            row_number=2,
        )
        self.assertEqual(row["source_type"], "government")
        self.assertEqual(row["source_authority_type"], "government")
        self.assertEqual(row["source_format"], "pdf")

    def test_internal_only_is_not_pack_ready(self):
        self.assertFalse(is_pack_ready("internal_only", "needs_review"))
        self.assertFalse(is_pack_ready("publishable", "needs_review"))


class TreeIdMigrationTests(unittest.TestCase):
    def test_existing_tree_id_records_backfill_to_internal_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = FoundryConfig(
                data_root=root,
                intake_db=root / "intake.db",
                repository_db=root / "repository.db",
                vault_root=root / "vault",
                host="127.0.0.1",
                port=8790,
            )
            bootstrap_workspace(config)
            queue = CandidateIntakeQueue(config.intake_db)
            local_file = root / "tree.pdf"
            local_file.write_text("tree", encoding="utf-8")
            queue.submit_candidate(
                title="Tree ID Presentation (Hart)",
                publisher="Unknown",
                source_type="university",
                submitted_by="Andrew",
                mission_id="mission:foundry:outdoor:trees",
                coverage_object_id="cov:ogm.pack.north-american-outdoor:species:trees",
                proposed_canonical_reference_type="image_diagram",
                local_file_path=local_file,
                license_status="needs_review",
                notes="First real Tree ID source intake test",
            )
            queue = CandidateIntakeQueue(config.intake_db)
            candidate = queue.list_candidates()[0]
            self.assertEqual(candidate["source_format"], "pdf")
            self.assertEqual(candidate["source_authority_type"], "university")
            self.assertEqual(candidate["publication_status"], "internal_only")
            self.assertFalse(candidate["pack_ready"])

    def test_dashboard_summary_includes_taxonomy_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = FoundryConfig(
                data_root=root,
                intake_db=root / "intake.db",
                repository_db=root / "repository.db",
                vault_root=root / "vault",
                host="127.0.0.1",
                port=8790,
            )
            bootstrap_workspace(config)
            queue = CandidateIntakeQueue(config.intake_db)
            local_file = root / "tree.pdf"
            local_file.write_text("tree", encoding="utf-8")
            queue.submit_candidate(
                title="Tree Guide",
                publisher="USFS",
                source_format="pdf",
                source_authority_type="government",
                source_type="government",
                submitted_by="Andrew",
                mission_id="mission:foundry:outdoor:trees",
                coverage_object_id="cov:ogm.pack.north-american-outdoor:species:trees",
                proposed_canonical_reference_type="government_publication",
                local_file_path=local_file,
                license_status="needs_review",
                publication_status="internal_only",
            )
            summary = FoundryDataReader(config).dashboard_summary()
            item = summary["candidates"]["items"][0]
            self.assertEqual(item["source_format"], "pdf")
            self.assertEqual(item["license_status"], "needs_review")
            self.assertEqual(item["publication_status"], "internal_only")


class RealTreeIdWorkspaceTests(unittest.TestCase):
    def test_real_tree_id_workspace_records_remain_valid(self):
        config = FoundryConfig.from_env()
        if not config.intake_db.is_file():
            self.skipTest("Foundry workspace not present")
        queue = CandidateIntakeQueue(config.intake_db)
        candidates = queue.list_candidates()
        if len(candidates) < 2:
            self.skipTest("Expected Tree ID candidates not present")
        for candidate in candidates:
            self.assertIn(candidate["source_format"], {"pdf", "slide_deck", "unknown"})
            self.assertTrue(candidate["source_authority_type"])
            self.assertEqual(candidate["license_status"], "needs_review")
            self.assertEqual(candidate["publication_status"], "internal_only")
            self.assertFalse(candidate["pack_ready"])

        ledger = IntakeLedger(config.intake_db)
        for source in ledger.list_sources():
            publication_status = source.get("publication_status") or source["metadata"].get("publication_status")
            self.assertEqual(source.get("license"), "needs_review")
            self.assertEqual(publication_status, "internal_only")
            self.assertFalse(source["metadata"].get("pack_ready", False))


class _FakeCoverage:
    def get_coverage_object(self, coverage_object_id: str) -> dict:
        return {
            "coverage_object_id": coverage_object_id,
            "domain": "outdoor",
            "subcategory": "trees",
        }


if __name__ == "__main__":
    unittest.main()
