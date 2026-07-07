const REFRESH_MS = 30000;

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return new Intl.NumberFormat().format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(Number(value) * 1000) / 10}%`;
}

function formatBytes(value) {
  if (!value) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function renderPills(containerId, entries) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = "";
  const items = Object.entries(entries || {}).filter(([, count]) => count > 0);
  if (!items.length) {
    container.innerHTML = '<span class="pill">No records</span>';
    return;
  }
  for (const [label, count] of items) {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.innerHTML = `${label}<strong>${formatNumber(count)}</strong>`;
    container.appendChild(pill);
  }
}

function renderStack(containerId, items, renderItem) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = '<div class="stack-item"><div class="stack-item-meta">No records yet.</div></div>';
    return;
  }
  for (const item of items) {
    container.appendChild(renderItem(item));
  }
}

function badgeClass(kind, value) {
  const normalized = String(value || "").toLowerCase();
  if (kind === "license" && (normalized === "needs_review" || normalized === "restricted" || normalized === "rejected")) {
    return "badge badge-warn";
  }
  if (kind === "publication" && (normalized === "internal_only" || normalized === "not_publishable")) {
    return "badge badge-warn";
  }
  if (kind === "publication" && (normalized === "publishable" || normalized === "pack_ready")) {
    return "badge badge-ok";
  }
  return "badge";
}

function renderBadge(value, kind) {
  const label = value || "unknown";
  return `<span class="${badgeClass(kind, label)}">${label}</span>`;
}

function renderMessage(id, message) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = message || "";
  }
}

async function fetchSummary() {
  const response = await fetch("/api/dashboard/summary", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Dashboard request failed (${response.status})`);
  }
  return response.json();
}

function renderDashboard(data) {
  const health = data.health || {};
  const repository = data.repository || {};
  const coverage = data.coverage || {};
  const crsRequirements = data.crs_requirements || {};
  const missions = data.missions || {};
  const candidateQueue = data.candidate_queue || {};
  const candidates = data.candidates || {};
  const vault = data.vault || {};
  const curator = data.curator || {};
  const events = data.recent_events || {};

  setText("generated-at", data.generated_at || "—");
  setText("health-status", health.status === "ok" ? "System healthy" : "System degraded");
  document.getElementById("health-status").className = `meta-chip ${health.status === "ok" ? "status-ok" : "status-degraded"}`;

  setText("metric-knowledge-objects", formatNumber(repository.knowledge_objects));
  setText("metric-coverage-objects", formatNumber(coverage.total));
  setText("metric-active-missions", formatNumber(missions.active));
  setText("metric-candidate-queue", formatNumber(candidateQueue.total));
  setText("metric-vault-sources", formatNumber(vault.sources));
  setText("metric-curator-recs", formatNumber(curator.recommendations_total));

  setText("metric-knowledge-foot", repository.message || "Repository summary");
  setText("metric-coverage-foot", coverage.message || "Coverage matrix");
  setText("metric-missions-foot", missions.message || "Operational missions");
  setText("metric-candidate-foot", candidateQueue.message || "Manual intake queue");
  setText("metric-vault-foot", vault.message || "Raw source vault");
  setText("metric-curator-foot", curator.message || "Curator-001 status");

  setText("repo-evidence", formatNumber(repository.evidence));
  setText("repo-relationships", formatNumber(repository.relationships));
  setText("repo-coverage-objects", formatNumber(repository.coverage_objects));
  renderPills("repo-status-list", repository.by_status);
  renderPills("repo-category-list", repository.by_category);
  renderMessage("repo-message", repository.message);

  setText("coverage-complete", formatNumber(coverage.complete));
  setText("coverage-partial", formatNumber(coverage.partial));
  setText("coverage-not-started", formatNumber(coverage.not_started));
  setText("coverage-average", formatPercent(coverage.average_coverage_percentage));
  setText("coverage-crs-total", formatNumber(crsRequirements.total_requirements));
  renderMessage("coverage-message", coverage.message);

  const coverageBody = document.getElementById("coverage-table-body");
  coverageBody.innerHTML = "";
  for (const item of coverage.items || []) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${item.title}</td>
      <td>${item.status}</td>
      <td class="mono">${formatPercent(item.coverage_percentage)}</td>
      <td class="mono">${formatNumber(item.required_crs_count)}</td>
    `;
    coverageBody.appendChild(row);
  }

  renderStack("crs-requirements-list", crsRequirements.items || [], (item) => {
    const node = document.createElement("div");
    node.className = "stack-item";
    const requirementLabels = (item.requirements || [])
      .map((req) => req.label || req.reference_type)
      .join(" · ");
    const missingLabels = (item.missing_crs_requirements || [])
      .map((req) => req.label || req.reference_type)
      .join(" · ");
    node.innerHTML = `
      <div class="stack-item-title">${item.title}</div>
      <div class="stack-item-meta">${item.coverage_object_id} · ${formatNumber(item.required_crs_count)} CRS · ${formatNumber(item.missing_crs_count)} missing · ${formatPercent(item.coverage_percentage)} covered</div>
      <div class="stack-item-meta">Required: ${requirementLabels || "No CRS requirements"}</div>
      <div class="stack-item-meta">Missing: ${missingLabels || "None"}</div>
    `;
    return node;
  });
  renderMessage("crs-message", crsRequirements.message);

  renderStack("missions-list", missions.items || [], (mission) => {
    const node = document.createElement("div");
    node.className = "stack-item";
    node.innerHTML = `
      <div class="stack-item-title">${mission.title}</div>
      <div class="stack-item-meta">${mission.mission_id} · ${mission.status} · ${mission.target_pack_id || "no pack"}</div>
    `;
    return node;
  });
  renderMessage("missions-message", missions.message);

  renderPills("candidate-status-list", candidateQueue.by_status);
  setText("candidate-pending", formatNumber(candidateQueue.pending_review));
  setText("candidate-recommended", formatNumber(candidateQueue.recommended));
  setText("candidate-approved", formatNumber(candidateQueue.approved_for_intake));
  setText("candidate-rejected", formatNumber(candidateQueue.rejected));
  setText("candidate-duplicates", formatNumber(candidateQueue.duplicates));
  renderMessage("candidate-message", candidateQueue.message);

  const candidateBody = document.getElementById("candidate-table-body");
  candidateBody.innerHTML = "";
  for (const item of candidates.items || []) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${item.title}</td>
      <td>${item.status}</td>
      <td>${renderBadge(item.source_format, "format")}</td>
      <td>${renderBadge(item.source_authority_type || item.source_type, "authority")}</td>
      <td>${renderBadge(item.license_status, "license")}</td>
      <td>${renderBadge(item.publication_status, "publication")}</td>
      <td class="mono">${item.proposed_canonical_reference_type}</td>
    `;
    candidateBody.appendChild(row);
  }

  setText("vault-sources", formatNumber(vault.sources));
  setText("vault-revisions", formatNumber(vault.revisions));
  setText("vault-bytes", formatBytes(vault.archived_bytes));
  renderMessage("vault-message", vault.message);

  const vaultBody = document.getElementById("vault-table-body");
  if (vaultBody) {
    vaultBody.innerHTML = "";
    for (const item of vault.items || []) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${item.filename || "—"}</td>
        <td>${renderBadge(item.source_format, "format")}</td>
        <td>${renderBadge(item.source_authority_type, "authority")}</td>
        <td>${renderBadge(item.license_status, "license")}</td>
        <td>${renderBadge(item.publication_status, "publication")}</td>
      `;
      vaultBody.appendChild(row);
    }
  }

  setText("curator-agent", curator.agent_id || "—");
  setText("curator-scope", curator.scope || "—");
  setText("curator-mode", curator.mode || "—");
  setText("curator-recommendations", formatNumber(curator.recommendations_total));
  setText("curator-approvals", formatNumber(curator.approvals_approved));
  renderMessage("curator-message", curator.message);

  const eventsBody = document.getElementById("events-table-body");
  eventsBody.innerHTML = "";
  for (const event of events.items || []) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="mono">${event.timestamp || "—"}</td>
      <td>${event.source || "—"}</td>
      <td>${event.action || "—"}</td>
      <td class="mono">${event.entity_id || "—"}</td>
      <td>${event.actor || "—"}</td>
    `;
    eventsBody.appendChild(row);
  }
  renderMessage("events-message", events.message);

  setText("health-intake-db", health.backend?.intake_db ? "Available" : "Missing");
  setText("health-repository-db", health.backend?.repository_db ? "Available" : "Missing");
  setText("health-vault-root", health.backend?.vault_root ? "Available" : "Missing");
  setText("health-uptime", `${formatNumber(health.uptime_seconds)}s`);
  document.getElementById("health-intake-db").className = health.backend?.intake_db ? "status-ok" : "status-degraded";
  document.getElementById("health-repository-db").className = health.backend?.repository_db ? "status-ok" : "status-degraded";
  document.getElementById("health-vault-root").className = health.backend?.vault_root ? "status-ok" : "status-degraded";

  const capabilities = health.capabilities || {};
  const capabilityContainer = document.getElementById("health-capabilities");
  capabilityContainer.innerHTML = "";
  for (const [key, enabled] of Object.entries(capabilities)) {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = `${key.replaceAll("_", " ")}: ${enabled ? "enabled" : "disabled"}`;
    capabilityContainer.appendChild(pill);
  }
  renderStack("health-issues", (health.issues || []).map((issue) => ({ issue })), (item) => {
    const node = document.createElement("div");
    node.className = "stack-item";
    node.innerHTML = `<div class="stack-item-meta status-degraded">${item.issue}</div>`;
    return node;
  });
}

async function refreshDashboard() {
  try {
    const data = await fetchSummary();
    renderDashboard(data);
  } catch (error) {
    setText("health-status", "Dashboard unavailable");
    document.getElementById("health-status").className = "meta-chip status-bad";
    renderMessage("repo-message", String(error));
  }
}

document.getElementById("refresh-btn").addEventListener("click", refreshDashboard);
refreshDashboard();
setInterval(refreshDashboard, REFRESH_MS);
