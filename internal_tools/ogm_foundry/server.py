"""Foundry Dashboard v1.3 HTTP server."""

from __future__ import annotations

import json
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from internal_tools.ogm_foundry.config import FoundryConfig
from internal_tools.ogm_foundry.data import FoundryDataReader


PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_ROOT / "static"


class FoundryRequestHandler(SimpleHTTPRequestHandler):
    server_version = "OGMFoundry/1.3"

    def __init__(
        self,
        *args,
        reader_factory: Callable[[], FoundryDataReader] | None = None,
        static_dir: Path = STATIC_DIR,
        **kwargs,
    ) -> None:
        self.reader_factory = reader_factory or (lambda: FoundryDataReader())
        self.static_dir = static_dir
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed.path, parse_qs(parsed.query))
            return
        if parsed.path in {"/", ""}:
            self.serve_file(self.static_dir / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            relative = parsed.path.removeprefix("/static/")
            self.serve_file(self.static_dir / relative)
            return
        self.serve_file(self.static_dir / "index.html", "text/html; charset=utf-8")

    def handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        reader = self.reader_factory()

        if path == "/api/events/recent":
            limit = int(query.get("limit", ["20"])[0])
            self.send_json(reader.recent_events(limit=limit))
            return

        if path == "/api/events/timeline":
            entity_id = query.get("entity_id", [""])[0]
            if not entity_id:
                self.send_json({"error": "entity_id is required"}, status=400)
                return
            entity_type = query.get("entity_type", [None])[0]
            limit = int(query.get("limit", ["50"])[0])
            self.send_json(reader.entity_timeline(entity_type=entity_type, entity_id=entity_id, limit=limit))
            return

        detail_handlers = (
            ("/api/missions/", reader.mission_detail),
            ("/api/coverage/", reader.coverage_detail),
            ("/api/candidates/", reader.candidate_detail),
            ("/api/vault/sources/", reader.vault_source_detail),
            ("/api/evidence/", reader.evidence_detail),
        )
        for prefix, handler in detail_handlers:
            if path.startswith(prefix):
                entity_id = unquote(path[len(prefix) :])
                if not entity_id:
                    self.send_json({"error": "Missing entity id", "path": path}, status=400)
                    return
                try:
                    self.send_json(handler(entity_id))
                except KeyError as exc:
                    self.send_json({"error": str(exc)}, status=404)
                return

        routes = {
            "/api/dashboard/summary": reader.dashboard_summary,
            "/api/health": reader.health,
            "/api/missions": reader.missions,
            "/api/coverage": reader.coverage_objects,
            "/api/coverage/requirements": reader.coverage_requirements,
            "/api/candidates/counts": reader.candidate_counts,
            "/api/candidates": reader.candidates,
            "/api/repository/counts": reader.repository_counts,
            "/api/vault/counts": reader.vault_counts,
            "/api/curator/status": reader.curator_status,
        }
        handler = routes.get(path)
        if handler is None:
            self.send_json({"error": "Unknown API endpoint", "path": path}, status=404)
            return
        self.send_json(handler())

    def serve_file(self, file_path: Path, content_type: str | None = None) -> None:
        if not file_path.is_file():
            self.send_json({"error": "Not found", "path": str(file_path)}, status=404)
            return
        payload = file_path.read_bytes()
        mime = content_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, payload: object, *, status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:
        if str(args[0]).startswith("4") or str(args[0]).startswith("5"):
            super().log_message(format, *args)


def create_server(config: FoundryConfig | None = None) -> ThreadingHTTPServer:
    config = config or FoundryConfig.from_env()
    reader_factory = lambda: FoundryDataReader(config)

    class BoundHandler(FoundryRequestHandler):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, reader_factory=reader_factory, **kwargs)

    return ThreadingHTTPServer((config.host, config.port), BoundHandler)


def main() -> None:
    config = FoundryConfig.from_env()
    config.data_root.mkdir(parents=True, exist_ok=True)
    server = create_server(config)
    print("Offgrid Minds Foundry Dashboard v1.3")
    print(f"Dashboard: http://{config.host}:{config.port}/")
    print(f"Intake DB: {config.intake_db}")
    print(f"Repository DB: {config.repository_db}")
    print(f"Vault:       {config.vault_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFoundry server stopped.")


if __name__ == "__main__":
    main()
