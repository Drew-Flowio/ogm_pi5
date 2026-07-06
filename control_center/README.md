# Offgrid Minds Agent Control Center MVP

> **Note:** The maintained copy lives at
> [`internal_tools/ogm_control_center/`](../internal_tools/ogm_control_center/).
> This top-level `control_center/` folder is a legacy snapshot kept for reference.

Local Mission Control dashboard for managing future Offgrid Minds agents before
autonomous research, pack compilation, or publishing exists.

This module is intentionally separate from the existing Pi/headset and desktop
assistant app code.

## Run

```bash
cd "control_center"
python3 server.py
```

Open:

```text
http://127.0.0.1:8787
```

Optional environment variables:

```bash
OGM_CONTROL_CENTER_PORT=8788 python3 server.py
OGM_CONTROL_CENTER_DB=/path/to/control_center.sqlite3 python3 server.py
```

## Database

Default database path:

```text
control_center/data/control_center.sqlite3
```

Tables:

- `missions`
- `mission_events`
- `source_candidates`
- `source_reviews`
- `coverage_items`
- `knowledge_debt`
- `agent_logs`
- `approvals`

## Current MVP Capabilities

- Local web dashboard.
- SQLite persistence.
- Create and view missions.
- Edit mission status with audit events and approval records.
- Add source candidates manually.
- Approve or reject source candidates.
- Track source class and source quality score.
- Track coverage items.
- Track Knowledge Debt.
- View mission events, agent logs, and approvals.
- Add manual CKO recommendation placeholders.
- Display guardrails for disabled autonomous crawling, publishing, and pack compilation.

## Explicitly Not Built Yet

- Research agents.
- Web crawling.
- Autonomous source acquisition.
- OCR or extraction.
- Knowledge Object generation.
- Expert Pack compilation.
- Expert Pack publishing.
- Any changes to the existing Pi5/headset app or iPhone app.

## Source of Truth

This MVP follows the approved Offgrid Minds specs under `docs/specs`, especially:

- `ogm-agent-control-center-spec-v1.md`
- `ogm-knowledge-factory-spec-v1.md`
- `ogm-chief-knowledge-officer-spec-v1.md`
