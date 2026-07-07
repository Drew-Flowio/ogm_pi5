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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
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
  if (kind === "authority" && normalized === "unknown") {
    return "badge badge-warn";
  }
  return "badge";
}

function renderBadge(value, kind) {
  const label = value || "unknown";
  return `<span class="${badgeClass(kind, label)}">${escapeHtml(label)}</span>`;
}

function renderMessage(id, message) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = message || "";
  }
}

function routePath(kind, id) {
  return `#/${kind}/${encodeURIComponent(id)}`;
}

function parseRoute() {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (!hash) {
    return { view: "dashboard" };
  }
  const [view, ...rest] = hash.split("/");
  return { view, id: rest.length ? decodeURIComponent(rest.join("/")) : null };
}

function navigate(route) {
  window.location.hash = route.startsWith("#") ? route : `#/${route}`;
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}) for ${path}`);
  }
  return response.json();
}

async function fetchSummary() {
  return fetchJson("/api/dashboard/summary");
}

function makeClickableRow(route, html) {
  const row = document.createElement("tr");
  row.className = "clickable-row";
  row.innerHTML = html;
  row.addEventListener("click", () => navigate(route));
  return row;
}

function makeClickableStackItem(route, html) {
  const node = document.createElement("div");
  node.className = "stack-item clickable-row";
  node.innerHTML = html;
  node.addEventListener("click", () => navigate(route));
  return node;
}

function renderLink(kind, id, label) {
  if (!id) {
    return escapeHtml(label || "—");
  }
  return `<a class="entity-link" href="${routePath(kind, id)}">${escapeHtml(label || id)}</a>`;
}

function renderField(label, value, { mono = false, html = false } = {}) {
  const content = html ? value : escapeHtml(value ?? "—");
  return `
    <div class="detail-field">
      <div class="detail-label">${escapeHtml(label)}</div>
      <div class="detail-value${mono ? " mono" : ""}">${content}</div>
    </div>
  `;
}

function renderPanel(title, tag, bodyHtml) {
  return `
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(title)}</h2>
        ${tag ? `<span class="panel-tag">${escapeHtml(tag)}</span>` : ""}
      </div>
      <div class="panel-body detail-fields">${bodyHtml}</div>
    </section>
  `;
}

function renderTimeline(items) {
  const container = document.getElementById("detail-timeline");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!items || !items.length) {
    container.innerHTML = '<div class="timeline-empty">No audit or review events recorded for this entity.</div>';
    return;
  }
  for (const event of items) {
    const node = document.createElement("article");
    node.className = "timeline-item";
    const details = event.details ? JSON.stringify(event.details, null, 2) : "";
    node.innerHTML = `
      <div class="timeline-time mono">${escapeHtml(event.timestamp || "—")}</div>
      <div class="timeline-body">
        <div class="timeline-title">${escapeHtml(event.action || "event")} · ${escapeHtml(event.source || "unknown")}</div>
        <div class="timeline-meta">${escapeHtml(event.actor || "—")} · ${escapeHtml(event.entity_type || "—")}</div>
        ${details ? `<pre class="timeline-details mono">${escapeHtml(details)}</pre>` : ""}
      </div>
    `;
    container.appendChild(node);
  }
}

function showDashboardView() {
  document.getElementById("dashboard-view")?.classList.remove("hidden");
  document.getElementById("detail-view")?.classList.add("hidden");
}

function showDetailView() {
  document.getElementById("dashboard-view")?.classList.add("hidden");
  document.getElementById("detail-view")?.classList.remove("hidden");
}

function renderCrsBlock(crs) {
  if (!crs) {
    return renderPanel("CRS Requirements", "None", renderField("Status", "No CRS data"));
  }
  const required = (crs.requirements || [])
    .map((req) => req.label || req.reference_type)
    .join(" · ");
  const missing = (crs.missing_crs_requirements || [])
    .map((req) => req.label || req.reference_type)
    .join(" · ");
  return renderPanel(
    "CRS Requirements",
    `${formatNumber(crs.required_crs_count)} required`,
    [
      renderField("Coverage", formatPercent(crs.coverage_percentage)),
      renderField("Missing count", formatNumber(crs.missing_crs_count)),
      renderField("Required", required || "None"),
      renderField("Missing", missing || "None"),
    ].join(""),
  );
}

function renderMissionDetail(data) {
  const mission = data.mission || {};
  document.getElementById("detail-kicker").textContent = "Mission detail";
  document.getElementById("detail-title").textContent = mission.title || data.mission_id;
  document.getElementById("detail-subtitle").textContent = data.mission_id;
  const coverageHtml = (data.coverage_objects || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("coverage", item.coverage_object_id)}">
          <div class="stack-item-title">${escapeHtml(item.title)}</div>
          <div class="stack-item-meta">${escapeHtml(item.coverage_object_id)} · ${escapeHtml(item.status)} · ${formatPercent(item.coverage_percentage)}</div>
        </div>`,
    )
    .join("");
  const candidateHtml = (data.candidates || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("candidates", item.candidate_id)}">
          <div class="stack-item-title">${escapeHtml(item.title)}</div>
          <div class="stack-item-meta">${escapeHtml(item.status)} · ${renderBadge(item.source_format, "format")} ${renderBadge(item.source_authority_type, "authority")}</div>
        </div>`,
    )
    .join("");
  document.getElementById("detail-content").innerHTML = [
    renderPanel(
      "Mission",
      mission.status || "unknown",
      [
        renderField("Mission ID", data.mission_id, { mono: true }),
        renderField("Status", mission.status),
        renderField("Target pack", mission.target_pack_id, { mono: true }),
        renderField("Created", mission.created_at, { mono: true }),
        renderField("Updated", mission.updated_at, { mono: true }),
      ].join(""),
    ),
    renderPanel("Linked coverage", `${(data.coverage_objects || []).length} objects`, coverageHtml || renderField("Coverage", "None")),
    renderCrsBlock((data.crs || [])[0]),
    renderPanel("Candidates", `${(data.candidates || []).length} records`, candidateHtml || renderField("Candidates", "None")),
    renderPanel(
      "Curator activity",
      `${(data.recommendations || []).length} recs`,
      [
        renderField("Recommendations", formatNumber((data.recommendations || []).length)),
        renderField("Approvals", formatNumber((data.approvals || []).length)),
      ].join(""),
    ),
  ].join("");
  bindDetailLinks();
  renderTimeline((data.timeline || {}).items || []);
}

function renderCoverageDetail(data) {
  const coverage = data.coverage_object || {};
  document.getElementById("detail-kicker").textContent = "Coverage detail";
  document.getElementById("detail-title").textContent = coverage.title || data.coverage_object_id;
  document.getElementById("detail-subtitle").textContent = data.coverage_object_id;
  const evidenceHtml = (data.evidence || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("evidence", item.evidence_uuid)}">
          <div class="stack-item-title">${escapeHtml(item.evidence_uuid)}</div>
          <div class="stack-item-meta">${escapeHtml(item.canonical_reference_type || "unknown CRS")} · ${escapeHtml(item.license_status || "unknown license")}</div>
        </div>`,
    )
    .join("");
  const candidateHtml = (data.candidates || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("candidates", item.candidate_id)}">
          <div class="stack-item-title">${escapeHtml(item.title)}</div>
          <div class="stack-item-meta">${escapeHtml(item.status)} · ${escapeHtml(item.proposed_canonical_reference_type)}</div>
        </div>`,
    )
    .join("");
  document.getElementById("detail-content").innerHTML = [
    renderPanel(
      "Coverage object",
      coverage.status || "unknown",
      [
        renderField("Coverage ID", data.coverage_object_id, { mono: true }),
        renderField("Domain", coverage.domain),
        renderField("Category", `${coverage.category}/${coverage.subcategory}`, { mono: true }),
        renderField("Coverage", formatPercent(coverage.coverage_percentage)),
        renderField(
          "Mission",
          data.mission ? data.mission.title : "—",
          { html: true, value: data.mission ? renderLink("missions", data.mission.mission_id, data.mission.title) : "—" },
        ),
      ].join(""),
    ),
    renderCrsBlock(data.crs),
    renderPanel("Evidence", `${(data.evidence || []).length} records`, evidenceHtml || renderField("Evidence", "None")),
    renderPanel("Candidates", `${(data.candidates || []).length} records`, candidateHtml || renderField("Candidates", "None")),
  ].join("");
  bindDetailLinks();
  renderTimeline((data.timeline || {}).items || []);
}

function renderCandidateDetail(data) {
  const candidate = data.candidate || {};
  document.getElementById("detail-kicker").textContent = "Candidate detail";
  document.getElementById("detail-title").textContent = candidate.title || data.candidate_id;
  document.getElementById("detail-subtitle").textContent = data.candidate_id;
  const warnings = (candidate.publication_warnings || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const evidenceHtml = (data.evidence || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("evidence", item.evidence_uuid)}">
          <div class="stack-item-title">${escapeHtml(item.evidence_uuid)}</div>
          <div class="stack-item-meta">${escapeHtml(item.canonical_reference_type || "unknown CRS")}</div>
        </div>`,
    )
    .join("");
  document.getElementById("detail-content").innerHTML = [
    renderPanel(
      "Candidate",
      candidate.status || "unknown",
      [
        renderField("Publisher", candidate.publisher),
        renderField("Status", candidate.status),
        renderField("Format", renderBadge(candidate.source_format, "format") , { html: true }),
        renderField("Authority", renderBadge(candidate.source_authority_type || candidate.source_type, "authority") , { html: true }),
        renderField("Legacy source_type", candidate.source_type, { mono: true }),
        renderField("CRS type", candidate.proposed_canonical_reference_type, { mono: true }),
        renderField("License", renderBadge(candidate.license_status, "license") , { html: true }),
        renderField("Publication", renderBadge(candidate.publication_status, "publication") , { html: true }),
        renderField("Pack ready", candidate.pack_ready ? "yes" : "no"),
        renderField("Mission", renderLink("missions", candidate.mission_id, candidate.mission_id) , { html: true }),
        renderField("Coverage", renderLink("coverage", candidate.coverage_object_id, candidate.coverage_object_id) , { html: true }),
        renderField("Submitted", candidate.submitted_at, { mono: true }),
        renderField("Authority score", candidate.authority_score),
        renderField("Authority reason", candidate.authority_reason),
        renderField("Risk notes", candidate.risk_notes),
        renderField("Notes", candidate.notes),
        warnings ? renderField("Publication warnings", `<ul class="warning-list">${warnings}</ul>`, { html: true }) : "",
      ].join(""),
    ),
    renderPanel(
      "Workflow links",
      "Human-in-the-loop",
      [
        renderField("Recommendation", data.recommendation?.recommendation_id || "—", { mono: true }),
        renderField("Approval", data.approval?.approval_id || "—", { mono: true }),
        renderField(
          "Vault source",
          data.vault_source?.uuid || "—",
          { html: true, value: data.vault_source ? renderLink("vault", data.vault_source.uuid, data.vault_source.filename || data.vault_source.uuid) : "—" },
        ),
      ].join(""),
    ),
    renderPanel("Evidence", `${(data.evidence || []).length} records`, evidenceHtml || renderField("Evidence", "None")),
    renderPanel(
      "Review events",
      `${(data.review_events || []).length} events`,
      (data.review_events || [])
        .map(
          (event) =>
            `<div class="stack-item"><div class="stack-item-title">${escapeHtml(event.to_status)}</div><div class="stack-item-meta mono">${escapeHtml(event.timestamp)} · ${escapeHtml(event.actor)}</div></div>`,
        )
        .join("") || renderField("Review events", "None"),
    ),
  ].join("");
  bindDetailLinks();
  renderTimeline((data.timeline || {}).items || []);
}

function renderVaultDetail(data) {
  const source = data.source || {};
  const metadata = source.metadata || {};
  document.getElementById("detail-kicker").textContent = "Vault source detail";
  document.getElementById("detail-title").textContent = source.filename || data.source_uuid;
  document.getElementById("detail-subtitle").textContent = data.source_uuid;
  const revisionHtml = (data.revisions || [])
    .map(
      (rev) =>
        `<div class="stack-item"><div class="stack-item-title mono">${escapeHtml(rev.revision_uuid)}</div><div class="stack-item-meta">v${escapeHtml(rev.revision_number)} · ${escapeHtml(rev.checksum || "—")}</div></div>`,
    )
    .join("");
  const evidenceHtml = (data.evidence || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("evidence", item.evidence_uuid)}">
          <div class="stack-item-title">${escapeHtml(item.evidence_uuid)}</div>
          <div class="stack-item-meta">${escapeHtml(item.canonical_reference_type || "unknown CRS")}</div>
        </div>`,
    )
    .join("");
  document.getElementById("detail-content").innerHTML = [
    renderPanel(
      "Vault source",
      source.processing_state || "archived",
      [
        renderField("Source UUID", data.source_uuid, { mono: true }),
        renderField("Filename", source.filename),
        renderField("Format", renderBadge(source.source_format || metadata.source_format, "format") , { html: true }),
        renderField("Authority", renderBadge(source.source_authority_type || metadata.source_authority_type, "authority") , { html: true }),
        renderField("Legacy source_type", metadata.legacy_source_type, { mono: true }),
        renderField("CRS type", source.canonical_reference_type, { mono: true }),
        renderField("License", renderBadge(source.license, "license") , { html: true }),
        renderField("Publication", renderBadge(source.publication_status || metadata.publication_status, "publication") , { html: true }),
        renderField("Pack ready", metadata.pack_ready ? "yes" : "no"),
        renderField(
          "Candidate",
          metadata.candidate_id || "—",
          { html: true, value: metadata.candidate_id ? renderLink("candidates", metadata.candidate_id, metadata.candidate_id) : "—" },
        ),
        renderField("Mission", renderLink("missions", source.mission_id, source.mission_id) , { html: true }),
        renderField("Checksum", source.checksum, { mono: true }),
        renderField("Created", source.created_at, { mono: true }),
      ].join(""),
    ),
    renderPanel("Revisions", `${(data.revisions || []).length} records`, revisionHtml || renderField("Revisions", "None")),
    renderPanel("Evidence", `${(data.evidence || []).length} records`, evidenceHtml || renderField("Evidence", "None")),
  ].join("");
  bindDetailLinks();
  renderTimeline((data.timeline || {}).items || []);
}

function renderEvidenceDetail(data) {
  const evidence = data.evidence || {};
  const provenance = (evidence.metadata || {}).provenance || {};
  document.getElementById("detail-kicker").textContent = "Evidence detail";
  document.getElementById("detail-title").textContent = data.evidence_uuid;
  document.getElementById("detail-subtitle").textContent = evidence.source_uuid || "—";
  const coverageHtml = (data.coverage_objects || [])
    .map(
      (item) =>
        `<div class="stack-item clickable-row" data-route="${routePath("coverage", item.coverage_object_id)}">
          <div class="stack-item-title">${escapeHtml(item.title)}</div>
          <div class="stack-item-meta">${escapeHtml(item.coverage_object_id)} · ${formatPercent(item.coverage_percentage)}</div>
        </div>`,
    )
    .join("");
  document.getElementById("detail-content").innerHTML = [
    renderPanel(
      "Evidence",
      provenance.canonical_reference_type || "repository",
      [
        renderField("Evidence UUID", data.evidence_uuid, { mono: true }),
        renderField("Source UUID", renderLink("vault", evidence.source_uuid, evidence.source_uuid) , { html: true }),
        renderField("Revision UUID", evidence.raw_revision_uuid, { mono: true }),
        renderField("CRS type", provenance.canonical_reference_type, { mono: true }),
        renderField("License", renderBadge(provenance.license, "license") , { html: true }),
        renderField("Quality score", provenance.source_quality_score),
        renderField("Mission", renderLink("missions", provenance.mission_id, provenance.mission_id) , { html: true }),
        renderField("Created", evidence.created_at, { mono: true }),
        renderField("Locator", JSON.stringify(evidence.locator || {}, null, 2), { mono: true }),
        renderField("Citation", JSON.stringify(evidence.citation || {}, null, 2), { mono: true }),
      ].join(""),
    ),
    renderPanel("Linked coverage", `${(data.coverage_objects || []).length} objects`, coverageHtml || renderField("Coverage", "None")),
    data.vault_source
      ? renderPanel(
          "Vault source",
          data.vault_source.filename || data.vault_source.uuid,
          [
            renderField("Filename", data.vault_source.filename),
            renderField("Format", renderBadge(data.vault_source.source_format, "format") , { html: true }),
            renderField("Authority", renderBadge(data.vault_source.source_authority_type, "authority") , { html: true }),
          ].join(""),
        )
      : "",
  ].join("");
  bindDetailLinks();
  renderTimeline((data.timeline || {}).items || []);
}

function bindDetailLinks() {
  document.querySelectorAll("[data-route]").forEach((node) => {
    node.addEventListener("click", () => navigate(node.getAttribute("data-route").replace(/^#?\/?/, "")));
  });
  document.querySelectorAll("a.entity-link").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(node.getAttribute("href").replace(/^#?\/?/, ""));
    });
  });
}

async function renderDetail(route) {
  showDetailView();
  document.getElementById("detail-title").textContent = "Loading…";
  document.getElementById("detail-content").innerHTML = "";
  renderTimeline([]);
  try {
    let data;
    if (route.view === "missions") {
      data = await fetchJson(`/api/missions/${encodeURIComponent(route.id)}`);
      renderMissionDetail(data);
    } else if (route.view === "coverage") {
      data = await fetchJson(`/api/coverage/${encodeURIComponent(route.id)}`);
      renderCoverageDetail(data);
    } else if (route.view === "candidates") {
      data = await fetchJson(`/api/candidates/${encodeURIComponent(route.id)}`);
      renderCandidateDetail(data);
    } else if (route.view === "vault") {
      data = await fetchJson(`/api/vault/sources/${encodeURIComponent(route.id)}`);
      renderVaultDetail(data);
    } else if (route.view === "evidence") {
      data = await fetchJson(`/api/evidence/${encodeURIComponent(route.id)}`);
      renderEvidenceDetail(data);
    } else {
      throw new Error(`Unknown detail view: ${route.view}`);
    }
    setText("detail-generated-at", new Date().toISOString().replace("+00:00", "Z"));
  } catch (error) {
    document.getElementById("detail-title").textContent = "Detail unavailable";
    document.getElementById("detail-subtitle").textContent = String(error);
    document.getElementById("detail-content").innerHTML = renderPanel("Error", "Read-only dashboard", renderField("Message", String(error)));
  }
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
    const coverageId = item.coverage_object_id;
    coverageBody.appendChild(
      makeClickableRow(
        `coverage/${encodeURIComponent(coverageId)}`,
        `
      <td>${escapeHtml(item.title)}</td>
      <td>${escapeHtml(item.status)}</td>
      <td class="mono">${formatPercent(item.coverage_percentage)}</td>
      <td class="mono">${formatNumber(item.required_crs_count)}</td>
    `,
      ),
    );
  }

  renderStack("crs-requirements-list", crsRequirements.items || [], (item) =>
    makeClickableStackItem(
      `coverage/${encodeURIComponent(item.coverage_object_id)}`,
      `
      <div class="stack-item-title">${escapeHtml(item.title)}</div>
      <div class="stack-item-meta">${escapeHtml(item.coverage_object_id)} · ${formatNumber(item.required_crs_count)} CRS · ${formatNumber(item.missing_crs_count)} missing · ${formatPercent(item.coverage_percentage)} covered</div>
    `,
    ),
  );
  renderMessage("crs-message", crsRequirements.message);

  renderStack("missions-list", missions.items || [], (mission) =>
    makeClickableStackItem(
      `missions/${encodeURIComponent(mission.mission_id)}`,
      `
      <div class="stack-item-title">${escapeHtml(mission.title)}</div>
      <div class="stack-item-meta">${escapeHtml(mission.mission_id)} · ${escapeHtml(mission.status)} · ${escapeHtml(mission.target_pack_id || "no pack")}</div>
    `,
    ),
  );
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
    candidateBody.appendChild(
      makeClickableRow(
        `candidates/${encodeURIComponent(item.candidate_id)}`,
        `
      <td>${escapeHtml(item.title)}</td>
      <td>${escapeHtml(item.status)}</td>
      <td>${renderBadge(item.source_format, "format")}</td>
      <td>${renderBadge(item.source_authority_type || item.source_type, "authority")}</td>
      <td>${renderBadge(item.license_status, "license")}</td>
      <td>${renderBadge(item.publication_status, "publication")}</td>
      <td class="mono">${escapeHtml(item.proposed_canonical_reference_type)}</td>
    `,
      ),
    );
  }

  setText("vault-sources", formatNumber(vault.sources));
  setText("vault-revisions", formatNumber(vault.revisions));
  setText("vault-bytes", formatBytes(vault.archived_bytes));
  renderMessage("vault-message", vault.message);

  const vaultBody = document.getElementById("vault-table-body");
  if (vaultBody) {
    vaultBody.innerHTML = "";
    for (const item of vault.items || []) {
      vaultBody.appendChild(
        makeClickableRow(
          `vault/${encodeURIComponent(item.source_uuid)}`,
          `
        <td>${escapeHtml(item.filename || "—")}</td>
        <td>${renderBadge(item.source_format, "format")}</td>
        <td>${renderBadge(item.source_authority_type, "authority")}</td>
        <td>${renderBadge(item.license_status, "license")}</td>
        <td>${renderBadge(item.publication_status, "publication")}</td>
      `,
        ),
      );
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
    const entityId = event.entity_id;
    const route = entityId ? `${entityRouteForEvent(event)}/${encodeURIComponent(entityId)}` : null;
    const row = route
      ? makeClickableRow(
          route,
          `
      <td class="mono">${escapeHtml(event.timestamp || "—")}</td>
      <td>${escapeHtml(event.source || "—")}</td>
      <td>${escapeHtml(event.action || "—")}</td>
      <td class="mono">${escapeHtml(entityId || "—")}</td>
      <td>${escapeHtml(event.actor || "—")}</td>
    `,
        )
      : document.createElement("tr");
    if (!route) {
      row.innerHTML = `
      <td class="mono">${escapeHtml(event.timestamp || "—")}</td>
      <td>${escapeHtml(event.source || "—")}</td>
      <td>${escapeHtml(event.action || "—")}</td>
      <td class="mono">${escapeHtml(entityId || "—")}</td>
      <td>${escapeHtml(event.actor || "—")}</td>
    `;
      eventsBody.appendChild(row);
    } else {
      eventsBody.appendChild(row);
    }
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
    node.innerHTML = `<div class="stack-item-meta status-degraded">${escapeHtml(item.issue)}</div>`;
    return node;
  });
}

function entityRouteForEvent(event) {
  const entityType = String(event.entity_type || "").toLowerCase();
  const entityId = String(event.entity_id || "");
  if (entityType.includes("candidate") || entityId.startsWith("cand:")) {
    return "candidates";
  }
  if (entityType.includes("evidence") || entityId.startsWith("ev:")) {
    return "evidence";
  }
  if (entityType.includes("source") || entityId.startsWith("src:")) {
    return "vault";
  }
  if (entityType.includes("coverage") || entityId.startsWith("cov:")) {
    return "coverage";
  }
  if (entityType.includes("mission") || entityId.startsWith("mission:")) {
    return "missions";
  }
  return "timeline";
}

async function refreshDashboard() {
  const route = parseRoute();
  if (route.view !== "dashboard" && route.id) {
    await renderDetail(route);
    return;
  }
  showDashboardView();
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
document.getElementById("detail-back-btn").addEventListener("click", () => navigate(""));
window.addEventListener("hashchange", refreshDashboard);
refreshDashboard();
setInterval(refreshDashboard, REFRESH_MS);
