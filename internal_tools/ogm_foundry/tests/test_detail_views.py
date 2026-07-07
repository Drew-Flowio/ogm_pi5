import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from internal_tools.ogm_foundry.bootstrap_workspace import bootstrap_workspace
from internal_tools.ogm_foundry.config import FoundryConfig
from internal_tools.ogm_foundry.data import FoundryDataReader
from internal_tools.ogm_foundry.server import create_server
from internal_tools.ogm_foundry.workspace_spec import WORKSPACE_TOPICS
from internal_tools.ogm_milestone_001.candidate_queue import CandidateIntakeQueue


class FoundryDetailReaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = FoundryConfig(
            data_root=self.root,
            intake_db=self.root / "intake.db",
            repository_db=self.root / "repository.db",
            vault_root=self.root / "vault",
            host="127.0.0.1",
            port=8790,
        )
        bootstrap_workspace(self.config)
        self.trees = WORKSPACE_TOPICS[0]
        self.local_file = self.root / "guide.pdf"
        self.local_file.write_text("tree guide", encoding="utf-8")
        queue = CandidateIntakeQueue(self.config.intake_db)
        self.candidate = queue.submit_candidate(
            title="Tree Guide",
            publisher="USFS",
            source_format="pdf",
            source_authority_type="government",
            source_type="government",
            submitted_by="Andrew",
            mission_id=self.trees.mission_id,
            coverage_object_id=self.trees.coverage_object_id,
            proposed_canonical_reference_type="government_publication",
            local_file_path=self.local_file,
            license_status="needs_review",
            publication_status="internal_only",
        )
        self.reader = FoundryDataReader(self.config)

    def tearDown(self):
        self._tmp.cleanup()

    def test_mission_detail_includes_candidates_and_crs(self):
        detail = self.reader.mission_detail(self.trees.mission_id)
        self.assertEqual(detail["mission_id"], self.trees.mission_id)
        self.assertEqual(len(detail["coverage_objects"]), 1)
        self.assertEqual(len(detail["candidates"]), 1)
        self.assertIn("requirements", detail["crs"][0])

    def test_coverage_detail_includes_mission_and_candidates(self):
        detail = self.reader.coverage_detail(self.trees.coverage_object_id)
        self.assertEqual(detail["coverage_object"]["title"], "Trees")
        self.assertEqual(detail["mission"]["mission_id"], self.trees.mission_id)
        self.assertEqual(len(detail["candidates"]), 1)
        self.assertIn("requirements", detail["crs"])

    def test_candidate_detail_includes_review_timeline(self):
        detail = self.reader.candidate_detail(self.candidate["candidate_id"])
        self.assertEqual(detail["candidate"]["title"], "Tree Guide")
        self.assertGreaterEqual(len(detail["review_events"]), 1)
        self.assertIn("items", detail["timeline"])

    def test_entity_timeline_filters_candidate_events(self):
        timeline = self.reader.entity_timeline(entity_id=self.candidate["candidate_id"], limit=20)
        self.assertGreaterEqual(timeline["count"], 1)
        self.assertTrue(any(item["entity_id"] == self.candidate["candidate_id"] for item in timeline["items"]))

    def test_missing_mission_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.reader.mission_detail("mission:missing")


class FoundryDetailApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = FoundryConfig(
            data_root=self.root,
            intake_db=self.root / "intake.db",
            repository_db=self.root / "repository.db",
            vault_root=self.root / "vault",
            host="127.0.0.1",
            port=0,
        )
        bootstrap_workspace(self.config)
        self.trees = WORKSPACE_TOPICS[0]
        queue = CandidateIntakeQueue(self.config.intake_db)
        local_file = self.root / "guide.pdf"
        local_file.write_text("tree guide", encoding="utf-8")
        self.candidate = queue.submit_candidate(
            title="Tree Guide",
            publisher="USFS",
            source_format="pdf",
            source_authority_type="government",
            source_type="government",
            submitted_by="Andrew",
            mission_id=self.trees.mission_id,
            coverage_object_id=self.trees.coverage_object_id,
            proposed_canonical_reference_type="government_publication",
            local_file_path=local_file,
            license_status="needs_review",
            publication_status="internal_only",
        )
        self.server = create_server(self.config)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def _get(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_candidate_detail_api(self):
        candidate_id = self.candidate["candidate_id"]
        status, payload = self._get(f"/api/candidates/{candidate_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["candidate_id"], candidate_id)
        self.assertEqual(payload["candidate"]["title"], "Tree Guide")

    def test_mission_detail_api(self):
        status, payload = self._get(f"/api/missions/{self.trees.mission_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["mission"]["title"], self.trees.mission_title)

    def test_coverage_detail_api(self):
        status, payload = self._get(f"/api/coverage/{self.trees.coverage_object_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["coverage_object"]["subcategory"], "trees")

    def test_timeline_api(self):
        status, payload = self._get(
            f"/api/events/timeline?entity_id={self.candidate['candidate_id']}&limit=10"
        )
        self.assertEqual(status, 200)
        self.assertIn("items", payload)

    def test_missing_detail_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/candidates/cand:missing")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
