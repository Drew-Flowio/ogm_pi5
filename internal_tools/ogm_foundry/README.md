# Offgrid Minds Foundry Dashboard v1.3

Foundry is the internal Mission Control dashboard for the Offgrid Minds knowledge
factory. It reads real data from the Milestone 1–6 backend in
`internal_tools/ogm_milestone_001`.

Foundry is separate from the Pi5 app, iPhone app, and older control center MVPs.

## What Foundry Does

- Serves a local read-only dashboard UI
- Bootstraps a real North American Outdoor Expert Pack workspace
- Accepts manually submitted candidate sources via CSV import
- Runs Curator-001 evaluation from the CLI (no auto-approval)
- Records human approvals from the CLI
- Vaults approved local-file candidates and bridges them to repository evidence
- Shows real missions, coverage objects, CRS requirements, queue counts, vault counts, and audit events
- Does not crawl, auto-approve, auto-vault, publish, or compile packs

## Step-By-Step Real Source Workflow

### 1. Bootstrap the workspace

From the repository root:

```bash
python3 -m internal_tools.ogm_foundry.bootstrap_workspace
```

This creates:

- Pack: `ogm.pack.north-american-outdoor`
- Coverage objects: Trees, Mushrooms, Camp Stoves, Water Purification, Weather Hazards, Navigation Basics
- Canonical Reference Standard requirements for each topic
- One active mission per coverage object

It does **not** create sources, approvals, vault records, knowledge objects, or fake activity.

Safety:

```bash
# Add missing records without deleting existing data
python3 -m internal_tools.ogm_foundry.bootstrap_workspace --force

# Delete and recreate the workspace (destructive)
python3 -m internal_tools.ogm_foundry.bootstrap_workspace --reset
```

Default workspace location:

```text
internal_tools/ogm_foundry/data/
  intake.db
  repository.db
  vault/
  workspace.json
```

Override with:

```bash
OGM_FOUNDRY_ROOT="/path/to/workspace" python3 -m internal_tools.ogm_foundry.bootstrap_workspace
```

After bootstrap, the dashboard shows six missions, six coverage objects, CRS requirement counts, and zero vault/repository activity.

### 2. Copy the candidate CSV template

```bash
cp internal_tools/ogm_foundry/templates/candidates.csv /path/to/my-candidates.csv
```

Required columns:

- `title`
- `publisher`
- `mission_id`
- `coverage_object_id`
- `proposed_canonical_reference_type`
- `submitted_by`
- `source_authority_type` **or** legacy `source_type`

Each row must include either `url` or `local_file_path`.

Recommended taxonomy columns (v1.25):

- `source_format` — file/container format (`pdf`, `html`, `image`, `slide_deck`, `book`, `manual`, `unknown`)
- `source_authority_type` — trust/authority category (`government`, `university`, `extension`, `manufacturer`, `professional_org`, `official_field_guide`, `commercial_expert`, `nonprofit`, `unknown`)
- `license_status` — `needs_review`, `internal_only`, `cleared`, `restricted`, `rejected`
- `publication_status` — `not_publishable`, `internal_only`, `publishable`, `pack_ready`

Legacy column (backward compatible):

- `source_type` — deprecated authority alias; still accepted on import. Prefer `source_authority_type` for new rows.

Optional columns:

- `license_notes`
- `authority_score`
- `authority_reason`
- `risk_notes`
- `notes`

If `source_format` is omitted, it is inferred from `local_file_path` or `url` when safe. Curator-001 evaluates **authority** from `source_authority_type`, not file format — a PDF from a government publisher is acceptable; a PDF with `unknown` authority is allowed into review with conservative risk notes.

Mission and coverage IDs are written to `workspace.json` after bootstrap.

### 3. Add a real candidate row

Edit the CSV with a real source you control or have rights to review. Example for Trees:

```csv
title,publisher,url,local_file_path,source_format,source_authority_type,source_type,mission_id,coverage_object_id,proposed_canonical_reference_type,submitted_by,license_status,publication_status,license_notes,authority_score,authority_reason,risk_notes,notes
USFS Red Maple Guide,United States Forest Service,,/path/to/usfs-trees.pdf,pdf,government,government,<mission_id>,<coverage_object_id>,government_publication,human:researcher:001,needs_review,publishable,To be verified manually.,0.95,Government forestry publisher.,,Real candidate for intake.
```

Use the mission and coverage object IDs from `workspace.json`.

### 4. Import candidates

```bash
python3 -m internal_tools.ogm_foundry.import_candidates /path/to/my-candidates.csv
```

Import behavior:

- validates required fields
- submits rows into `CandidateIntakeQueue`
- uses existing duplicate detection
- does not download URLs
- does not create human approvals
- does not vault sources automatically

Dry run:

```bash
python3 -m internal_tools.ogm_foundry.import_candidates /path/to/my-candidates.csv --dry-run
```

After import, the dashboard candidate queue shows `submitted` count increase and the candidate table lists the new row.

### 5. Evaluate candidates with Curator-001

```bash
python3 -m internal_tools.ogm_foundry.evaluate_candidates
```

Optional filters:

```bash
python3 -m internal_tools.ogm_foundry.evaluate_candidates --mission-id <mission_id>
python3 -m internal_tools.ogm_foundry.evaluate_candidates --coverage-object-id <coverage_object_id>
python3 -m internal_tools.ogm_foundry.evaluate_candidates --candidate-id <candidate_id>
```

This:

- loads submitted candidates
- runs Curator-001 evaluation using existing logic
- creates curator recommendations
- updates candidate status to `recommended` or `rejected`
- preserves review/audit history
- does **not** approve or vault anything automatically

After evaluation, the dashboard shows recommended/rejected counts and recent review events.

### 6. Approve a recommended candidate

```bash
python3 -m internal_tools.ogm_foundry.approve_candidate <candidate_id> \
  --actor Andrew \
  --notes "Approved as authoritative government forestry reference"
```

This:

- requires an existing curator recommendation
- creates a human approval record
- updates candidate status to `approved_for_intake`
- requires actor/reviewer name and approval notes
- preserves review/audit history

After approval, the dashboard shows `approved_for_intake` count and the candidate appears in the approved-waiting-for-vault list.

### 7. Intake an approved candidate (vault + repository bridge)

```bash
python3 -m internal_tools.ogm_foundry.intake_approved_candidate <candidate_id>
```

This:

- requires candidate status `approved_for_intake`
- requires human approval
- requires a valid `local_file_path` (URL-only candidates cannot be vaulted)
- archives the file into Raw Source Vault
- creates intake ledger records
- bridges to repository evidence via `approved_candidate_to_repository_evidence`
- links evidence to the coverage object
- runs CRS evaluation for the coverage object
- returns `source_uuid`, `revision_uuid`, and `evidence_uuid`
- preserves audit/ACP events where available

After intake, the dashboard shows vault source count, evidence count, updated coverage percentages, and recent vault/repository events.

### 8. Check workspace status

```bash
python3 -m internal_tools.ogm_foundry.workspace_status
```

JSON output:

```bash
python3 -m internal_tools.ogm_foundry.workspace_status --json
```

Prints missions count, coverage objects, CRS requirements, candidates by status, recommendations, approvals, vault sources, evidence, coverage percentages, and next recommended manual actions.

### 9. Refresh the dashboard

```bash
python3 -m internal_tools.ogm_foundry.server
```

Open:

```text
http://127.0.0.1:8790/
```

After the full workflow, verify:

- CRS requirements per coverage object (including missing CRS labels)
- candidate statuses in the queue table
- recommended candidates count
- approved candidates waiting for vault intake
- coverage percentages increased for the intaken topic
- recent candidate review events
- recent vault/repository events

## Run The Dashboard

```bash
python3 -m internal_tools.ogm_foundry.server
```

The dashboard is read-only. Approve and intake actions are CLI-only in v1.2.

## API Endpoints

| Endpoint | Description |
|---|---|
| `/api/dashboard/summary` | Combined dashboard payload |
| `/api/health` | Backend availability |
| `/api/missions` | Mission records |
| `/api/coverage` | Coverage objects |
| `/api/coverage/requirements` | CRS requirements by coverage object (including missing CRS) |
| `/api/candidates/counts` | Candidate queue counts |
| `/api/candidates` | Candidate list with statuses |
| `/api/repository/counts` | Repository counts |
| `/api/vault/counts` | Vault counts |
| `/api/curator/status` | Curator recommendation/approval counts |
| `/api/missions/{mission_id}` | Mission detail with CRS, candidates, timeline |
| `/api/coverage/{coverage_object_id}` | Coverage detail with CRS, evidence, candidates |
| `/api/candidates/{candidate_id}` | Candidate detail with review events and vault links |
| `/api/vault/sources/{source_uuid}` | Vault source detail with revisions and evidence |
| `/api/evidence/{evidence_uuid}` | Evidence detail with coverage and vault links |
| `/api/events/timeline?entity_id=...&limit=50` | Entity-scoped audit/review timeline |

## CLI Commands Summary

| Command | Purpose |
|---|---|
| `bootstrap_workspace` | Initialize real North American Outdoor workspace |
| `import_candidates <csv>` | Import manual candidate rows |
| `evaluate_candidates` | Run Curator-001 on submitted candidates |
| `approve_candidate <id> --actor --notes` | Record human approval |
| `intake_approved_candidate <id>` | Vault local file and bridge to repository |
| `workspace_status` | Print counts, coverage, and next actions |
| `server` | Serve read-only dashboard |

## Current Limitations

- Read-only dashboard (no edit/approve buttons in the web UI)
- No login/auth
- No browser upload UI
- CSV import is CLI-only
- URL-only candidates remain in the queue until a local file is available for vault intake
- Curator-001 evaluation is CLI-triggered, not automatic
- No OCR, embeddings, pack compilation, or autonomous crawling
- License strict review is optional (`strict_license_review=False` by default in intake CLI)

## Source Taxonomy and Publication Safety (v1.25)

Foundry v1.25 separates **file format** from **authority/trust** and adds publication safety metadata before pack compilation exists:

| Field | Purpose |
|---|---|
| `source_format` | How the source is stored (pdf, html, slide_deck, …) |
| `source_authority_type` | Who published it and how much to trust it |
| `proposed_canonical_reference_type` | CRS requirement matching (unchanged) |
| `license_status` | License review state |
| `publication_status` | Whether the source may ever ship in an Expert Pack |

Publication safety rules:

- `internal_only` and `not_publishable` sources are never treated as pack-ready
- `publication_warnings` are stored on vault intake for downstream pack tooling
- Existing candidates keep legacy `source_type`; migrations infer format/authority where safe

## Next Recommended Milestone

Foundry v1.3 adds read-only detail pages in the dashboard:

- Mission detail — linked coverage, CRS, candidates, curator activity
- Coverage detail — CRS matrix, linked evidence and candidates
- Candidate detail — taxonomy, workflow links, review events
- Vault source detail — revisions, evidence bridge, publication safety
- Evidence detail — provenance, coverage links, vault cross-refs
- Audit/review timeline — entity-scoped history on every detail page

Open the dashboard and click any mission, coverage row, candidate, vault source, or recent event to navigate. URLs use hash routes such as `#/candidates/cand:...`.

Foundry v1.4 should add:

- browser-based review UI with explicit approve/reject actions (still human-gated)
- workspace manifest panel with bootstrap metadata and file paths

## Tests

```bash
python3 -m unittest discover -s internal_tools/ogm_foundry/tests -v
python3 -m unittest discover -s internal_tools/ogm_milestone_001/tests -v
```
