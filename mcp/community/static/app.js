"use strict";
const $ = (s) => document.querySelector(s);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const badge = (s) =>
  `<span class="badge ${/^[a-z_]+$/.test(s) ? s : ""}">${esc(String(s || "unknown").replaceAll("_", " "))}</span>`;
const empty = (title, note = "") =>
  `<div class="empty"><strong>${esc(title)}</strong>${esc(note)}</div>`;
const date = (d) => (d ? new Date(d).toLocaleString() : "—");
let identity = null;
let token = "",
  snapshot = null,
  campaignId = "",
  route = "overview",
  streamControl,
  viewControl,
  scheduleMode = false;
let currentDetailJob = "", lastFindingsHash = "", jobDetailRequest = 0;
let jobRevealPending = false, jobRevealUntil = 0;
let findingDetailRequest = 0, currentFindingRef = "";
async function grantedRequest(kind, id, path) {
  const currentToken = token;
  const issued = await api("/api/v1/evidence/grants", {
    method: "POST",
    body: JSON.stringify({kind, id})
  });
  if (!token || token !== currentToken) throw new Error("Session changed");
  return api(path || `/api/v1/evidence/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/reveal`, {
    headers: {"X-Darkmoon-Evidence-Grant": issued.grant}
  });
}
function clearRevealedContent() {
  findingDetailRequest++;
  jobDetailRequest++;
  jobRevealPending = false;
  jobRevealUntil = 0;
  document.querySelectorAll("[data-revealed-content]").forEach(node => node.remove());
  const log = $("#job-log");
  if (log && log.dataset.revealedContent) {
    log.textContent = "Raw output cleared; use an explicit grant to reveal again.";
    delete log.dataset.revealedContent;
  }
}
let runQueueOffset = 0, runActiveOffset = 0, runQueueRequest = 0, runQueueControl;
const severityColors = {
  critical: "#fb8698",
  high: "#f5b27b",
  medium: "#e9d58b",
  low: "#a1e3bd",
  info: "#a6c8e7",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!response.ok) {
    const value = await response
      .json()
      .catch(() => ({ error: response.statusText }));
    if (response.status === 401) lock();
    throw new Error(value.error || "Request failed");
  }
  return response.json();
}
function fail(error) {
  $("#error").textContent = error.message;
  $("#error").hidden = false;
}
function lock() {
  clearRevealedContent();
  currentFindingRef = "";
  $("#detail").open && $("#detail").close();
  token = "";
  snapshot = null;
  identity = null;
  runQueueRequest++;
  runQueueControl?.abort();
  runQueueOffset = runActiveOffset = 0;
  streamControl?.abort();
  $("#setup-account").close();
  viewControl?.abort();
  $("#setup-account-form").reset();
  $("#login").showModal();
  $("#content").replaceChildren();
}
async function refresh() {
  clearRevealedContent();
  const [state, who] = await Promise.all([
    api("/api/v1/overview"),
    api("/api/v1/auth/me"),
  ]);
  snapshot = state;
  identity = who.user;
  if (!campaignId && snapshot.campaigns.length)
    campaignId = snapshot.campaigns.at(-1).id;
  $("#error").hidden = true;
  render();
}
async function connect() {
  streamControl?.abort();
  streamControl = new AbortController();
  while (token && !streamControl.signal.aborted) {
    try {
      const res = await fetch("/api/v1/events", {
        headers: { Authorization: `Bearer ${token}` },
        signal: streamControl.signal,
      });
      if (!res.ok) throw new Error("Live connection failed");
      $("#connection").textContent = "● Live";
      const reader = res.body.getReader(),
        decoder = new TextDecoder();
      let pending = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        let i;
        while ((i = pending.indexOf("\n\n")) >= 0) {
          const event = pending.slice(0, i);
          pending = pending.slice(i + 2);
          if (event.startsWith("event: revision")) await refresh();
        }
      }
    } catch (e) {
      if (e.name === "AbortError") return;
      $("#connection").textContent = "Reconnecting…";
    }
    if (token) await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}
function campaignsTable(items) {
  if (!items.length)
    return empty(
      "No assessments yet",
      "Start an assessment or connect the existing shared data directory.",
    );
  const targets = new Map(snapshot.targets.map((t) => [t.id, t]));
  return `<div class="table-scroll"><table><thead><tr><th>ASSESSMENT / TARGET</th><th>STATUS</th><th>FINDINGS</th><th>RISK</th><th>STARTED</th></tr></thead><tbody>${[
    ...items,
  ]
    .reverse()
    .map(
      (c) =>
        `<tr class="clickable" data-campaign="${esc(c.id)}"><td>${esc(c.name || c.id)}<small>${esc(targets.get(c.target_id)?.host || c.target_id)}</small></td><td>${badge(c.status)}</td><td>${snapshot.findings.filter((f) => f.campaign_id === c.id).length}</td><td>${badge(c.overall_risk || "none")}</td><td>${esc(date(c.date))}</td></tr>`,
    )
    .join("")}</tbody></table></div>`;
}
function campaignSelect() {
  return `<select id="campaign-select" aria-label="Campaign"><option value="">Choose assessment</option>${[
    ...snapshot.campaigns,
  ]
    .reverse()
    .map(
      (c) =>
        `<option value="${esc(c.id)}" ${campaignId === c.id ? "selected" : ""}>${esc(c.name || c.id)}</option>`,
    )
    .join("")}</select>`;
}
function findingsTable(items) {
  if (!items.length)
    return empty(
      "No findings in this view",
      "Findings appear as agents record evidence.",
    );
  return `<div class="table-scroll"><table><thead><tr><th>SEVERITY</th><th>FINDING / ENDPOINT</th><th>CVSS</th><th>STATUS</th><th>MITRE ATT&CK</th></tr></thead><tbody>${items.map((f) => `<tr class="clickable" data-finding="${esc(f.id)}" data-cid="${esc(f.campaign_id)}"><td>${badge(f.severity || "unknown")}</td><td><button class="text-button finding-open" data-finding="${esc(f.id)}" data-cid="${esc(f.campaign_id)}">${esc(f.title || "Untitled")}</button><small>${esc(f.endpoint || f.category || "")}</small></td><td>${esc(f.cvss_score ?? "—")}</td><td>${badge(f.status)}</td><td>${esc(f.mitre_attack_id || "—")}</td></tr>`).join("")}</tbody></table></div>`;
}
function applyRoles() {
  const viewer = identity?.role === "viewer",
    admin = identity?.role === "admin";
  $("#new-campaign").hidden = viewer;
  for (const a of document.querySelectorAll(
    'nav a[href="#credentials"],nav a[href="#webhooks"]',
  ))
    a.hidden = !admin;
  for (const b of document.querySelectorAll(
    '[data-workspace]:not([data-workspace="password"]),#new-schedule,[data-toggle-schedule],[data-delete-schedule],[data-edit-schedule],[data-duplicate-schedule],[data-cancel],[data-prepare-fix],[data-triage],#triage-status,[data-protected-pdf]',
  ))
    b.hidden = viewer;
}
function render() {
  if (!snapshot) return;
  viewControl?.abort();
  viewControl = new AbortController();
  route = location.hash.slice(1).split("?")[0] || "overview";
  const headings = {
    overview: "Overview",
    campaigns: "Campaigns",
    findings: "Findings",
    surface: "Attack surface",
    schedules: "Schedules",
    remediation: "Remediation",
    integrations: "Integrations",
    projects: "Projects & analytics",
    retests: "Retests",
    credentials: "Credentials",
    webhooks: "Webhooks",
    settings: "Settings & accounts",
  };
  if (!headings[route]) route = "overview";
  if (identity?.role !== "admin" && ["credentials", "webhooks"].includes(route))
    route = "settings";
  $("#heading").textContent = headings[route];
  document
    .querySelectorAll("nav a")
    .forEach((a) => a.classList.toggle("active", a.hash === `#${route}`));
  const s = snapshot,
    total = s.findings.length;
  if (route === "overview") {
    $("#content").innerHTML = window.PostureUI.render(s, {esc, badge, date, empty});
    if (new URLSearchParams(location.hash.split("?")[1]).get("targets") === "all") $("#posture-targets").scrollIntoView();
  } else if (route === "campaigns") {
    $("#content").innerHTML =
      `<section class="panel flush"><div class="section-top"><div><h3>All assessments</h3><p>Select one to review its findings, report and infrastructure.</p></div></div>${campaignsTable(s.campaigns)}</section><section class="panel"><div class="section-top"><h3>Execution queue and run logs</h3><span class="subtle">Lifecycle metadata; raw output restricted</span></div><div id="run-queue" role="status">Loading runs…</div></section>`;
    loadRunQueue(viewControl.signal);
  } else if (route === "findings") {
    renderFindings();
  } else if (route === "surface") {
    $("#content").innerHTML =
      `<div class="toolbar">${campaignSelect()}<button class="secondary" id="vr-button" disabled>Checking VR…</button><button class="secondary" id="surface-tour">Tour finding locations</button></div><div class="panel"><div class="map-layout"><div class="surface-stage"><div id="surface-controls"></div><canvas id="surface-canvas" class="surface" aria-label="Interactive three dimensional infrastructure graph"></canvas><div id="surface-tour-card" hidden></div><p class="map-caption">Drag to orbit · Scroll to zoom · Select a node to inspect. Lines show recorded containment and connections.</p></div><div class="map-info" id="map-info">Choose an assessment to explore its infrastructure.</div></div></div><section id="recorded-paths" class="panel"></section>`;
    if (campaignId) drawSurface(campaignId, viewControl.signal).catch(fail);
  } else if (route === "schedules") {
    $("#content").innerHTML = `<section class="panel"><div class="section-top"><div><h3>Scheduled assessments</h3><p>Calendar rules use their named timezone; elapsed intervals keep their existing timing. Missed occurrences coalesce and overlapping jobs are skipped.</p></div><button class="primary" id="new-schedule">+ Add schedule</button></div><p class="instructions">Duplicates start paused. Pause/delete prevents future claims; an occurrence already being enqueued or running may continue. Consumed one-time schedules can be explicitly re-armed.</p>${window.ScheduleUI.table(s.schedules)}</section>`;
  } else if (route === "remediation") {
    const query = new URLSearchParams(location.hash.split("?")[1] || "");
    const selectedStatus = query.get("status"), linkedOnly = query.get("linked") === "1";
    const retainedCampaigns = new Set(s.campaigns.map(c => c.id));
    const linked = new Set(s.findings.filter(f => f.id && retainedCampaigns.has(f.campaign_id)).map(f => JSON.stringify([f.campaign_id, f.id])));
    const proposals = s.remediations.filter(p => (!selectedStatus || (p.status || "unknown") === selectedStatus) && (!linkedOnly || linked.has(JSON.stringify([p.campaign_id, p.finding_id]))));
    $("#content").innerHTML =
      `<section class="panel"><div class="section-top"><div><h3>Local remediation proposals</h3><p>Patches and validation evidence, prepared for your review.</p></div><span class="badge">Publishing disabled</span></div><p class="instructions">Use the remediation command with a local source repository and a confirmed finding. It creates an isolated Git worktree, applies structured edits, and can run before/after regression probes in disposable Docker containers. Add <code>--generate</code> to use your configured model. No branch is pushed and no PR is opened.</p><pre>PYTHONPATH=mcp python3 -m community.remediation \
  --repo /path/to/target-source --campaign-id CAMPAIGN_ID \
  --finding-id FINDING_ID --edits /path/to/edits.json --validate</pre>${selectedStatus || linkedOnly ? `<p class="instructions">${proposals.length} matching proposals · ${esc(selectedStatus || "all statuses")} · ${linkedOnly ? "linked to retained findings" : "all records"}. <a class="metric-link" href="#remediation">Clear filters</a></p>` : ""}${proposals.length ? proposals.map((r) => `<div class="list-item"><div><a class="clickable" data-remediation="${esc(r.id)}">${esc(r.title || r.finding_id)}</a><small>${esc(r.branch || r.id)} · ${esc(date(r.created_at))}</small></div>${badge(r.status)}</div>`).join("") : empty("No proposals yet", "Proposals appear here when the local remediation command completes.")}</section>`;
  } else if (route === "integrations") {
    window.renderIntegrations().catch(fail);
  } else if (window.renderWorkspace) {
    window.renderWorkspace(route).then(applyRoles).catch(fail);
  }
  applyRoles();
}

function updateFindingView(changes, push = false) {
  const state = {...FindingQuery.read(location.hash), ...changes};
  const hash = FindingQuery.hash(state);
  if (hash !== location.hash) history[push ? "pushState" : "replaceState"](null, "", hash);
  render();
}
function renderFindings() {
  const state = FindingQuery.read(location.hash), result = FindingQuery.page(snapshot.findings, state);
  state.page = result.page;
  const canonical = FindingQuery.hash(state);
  if (location.hash !== canonical) history.replaceState(null, "", canonical);
  lastFindingsHash = canonical;
  const choices = (key, label, options) => {
    if (state[key] && !options.some(([value]) => value === state[key])) options.push([state[key], `Unavailable: ${state[key]}`]);
    const id = key === "severity" ? "severity-filter" : `finding-${key}-filter`;
    return `<label for="${id}">${esc(label)}<select id="${id}" data-finding-filter="${key}"><option value="">All ${esc(label.toLowerCase())}</option>${options.map(([value,title]) => `<option value="${esc(value)}" ${state[key] === value ? "selected" : ""}>${esc(title)}</option>`).join("")}</select></label>`;
  };
  const distinct = key => [...new Set(snapshot.findings.map(f => String(f[key] || ({severity:"unknown",status:"unconfirmed"})[key] || "")).filter(Boolean))].sort().map(value => [value,value.replaceAll("_"," ")]);
  const severityOptions = [...new Map([...Object.keys(severityColors).map(key => [key,key]), ...distinct("severity")])];
  const sortNames = {severity:"Severity",cvss:"CVSS",title:"Title",status:"Status",campaign:"Campaign ID",target:"Target ID"};
  $("#content").innerHTML = `<div class="findings-controls"><label for="finding-search">Search findings<input id="finding-search" aria-label="Search findings" maxlength="500" placeholder="Title, endpoint, category or ID…" value="${esc(state.q)}"></label>${choices("severity","Severities",severityOptions)}${choices("status","Statuses",distinct("status"))}${choices("category","Categories",distinct("category"))}${choices("project_id","Projects",snapshot.projects.map(p=>[p.id,p.name||p.id]))}${choices("mitre_attack_id","MITRE techniques",distinct("mitre_attack_id"))}${choices("triage","Triage groups",[["active","Active exposure"],["excluded","Excluded from active exposure"]])}${choices("campaign_id","Campaigns",snapshot.campaigns.map(c=>[c.id,c.name||c.id]))}${choices("target_id","Targets",snapshot.targets.map(t=>[t.id,t.host||t.ip||t.id]))}<label for="finding-sort">Sort<select id="finding-sort">${FindingQuery.sorts.map(value=>{const [field,direction]=value.split("_");return `<option value="${value}" ${state.sort===value?"selected":""}>${sortNames[field]} · ${direction==="desc"?"descending":"ascending"}</option>`}).join("")}</select></label><label for="finding-size">Rows per page<select id="finding-size">${[5,10,25,50,100].map(size=>`<option ${state.size===size?"selected":""}>${size}</option>`).join("")}</select></label></div><div class="toolbar"><button class="secondary" id="findings-clear">Clear filters</button><span class="subtle" role="status" id="finding-count">${result.total ? result.offset+1 : 0}–${result.offset+result.items.length} of ${result.total} matching findings · ${snapshot.findings.length} total</span></div><section class="panel flush">${findingsTable(result.items)}</section><div class="toolbar" aria-label="Finding pages"><button class="secondary" data-findings-page="${result.page-1}" ${result.page===1?"disabled":""}>Previous page</button><span>Page ${result.page} of ${result.pages}</span><button class="secondary" data-findings-page="${result.page+1}" ${result.page===result.pages?"disabled":""}>Next page</button></div>`;
}

async function showCampaign(id) {
  campaignId = id;
  const c = await api(`/api/v1/campaigns/${encodeURIComponent(id)}`);
  $("#detail-title").textContent = c.name || c.id;
  $("#detail-body").innerHTML =
    `${badge(c.status)} ${c.analysis_origin?.kind === "owned-loopback-lab" ? `<span class="badge">Owned loopback lab · no LLM</span>` : ""} <span class="subtle">${esc(c.target?.host || "")} · ${esc(date(c.date))}</span><div class="report-actions">${["md", "pdf", "json"].map((format) => `<button class="secondary" data-export="${format}" data-cid="${esc(id)}">Download ${format.toUpperCase()}</button>`).join("")}<button class="secondary" data-report-preview="${esc(id)}">Preview report</button><button class="secondary" data-protected-pdf="${esc(id)}">Signed / encrypted PDF</button><button class="secondary" id="open-map">Explore surface →</button></div><p class="detail-text">${esc(c.executive_summary || "No executive summary recorded yet.")}</p>${findingsTable(c.findings)}`;
  $("#detail").showModal();
}
function evidenceMarkup(evidence) {
  const pretty = (value) => {
    const text =
      typeof value === "string"
        ? value
        : Array.isArray(value)
          ? value
              .map((v) =>
                typeof v === "string" ? v : JSON.stringify(v, null, 2),
              )
              .join("\n")
          : JSON.stringify(value, null, 2);
    return (text || "")
      .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
      .replace(/\r+\n/g, "\n")
      .replace(/\r/g, "\n");
  };
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence))
    return `<pre>${esc(pretty(evidence) || "No evidence recorded")}</pre>`;
  return (
    Object.entries(evidence)
      .filter(([, value]) => value != null && value !== "")
      .map(
        ([key, value]) =>
          `<div class="detail-label">${esc(key.replaceAll("_", " "))}</div><pre data-evidence-field="${esc(key)}">${esc(pretty(value))}</pre>`,
      )
      .join("") +
    `<details><summary>Raw evidence JSON</summary><pre>${esc(JSON.stringify(evidence, null, 2))}</pre></details>`
  );
}
async function showFinding(id, cid) {
  const request = ++findingDetailRequest, previousToken = token;
  currentFindingRef = `${cid}:${id}`;
  const c = await api(`/api/v1/campaigns/${encodeURIComponent(cid)}`),
    f = c.findings.find((x) => x.id === id);
  if (!f) throw new Error("Finding not found");
  const related = await api(`/api/v1/pull-requests/finding/${encodeURIComponent(id)}?campaign_id=${encodeURIComponent(cid)}`)
    .catch(() => null);
  if (request !== findingDetailRequest || previousToken !== token || currentFindingRef !== `${cid}:${id}`) return;
  $("#detail-title").textContent = f.title || f.id;
  const evidence = '<p class="instructions">Recorded evidence is withheld by the server until an administrator authorizes a scoped reveal.</p>';
  $("#detail-body").innerHTML =
    `${badge(f.severity)} ${badge(f.status)} <span class="subtle">CVSS ${esc(f.cvss_score ?? "—")} · ${esc(f.discovered_by_agent || "")}</span>${[
      ["Endpoint", f.endpoint],
      ["Description", f.description],
      [
        "MITRE ATT&CK",
        [f.mitre_attack_id, f.mitre_attack_name].filter(Boolean).join(" · "),
      ],
      ["ISO 27001", f.iso27001_control],
    ]
      .filter(([, v]) => v)
      .map(
        ([k, v]) =>
          `<div class="detail-label">${esc(k)}</div><div class="detail-text">${esc(v)}</div>`,
      )
      .join(
        "",
      )}<div class="detail-label">Recorded evidence</div>${evidence}${f.evidence_commands ? `<pre>${esc(f.evidence_commands)}</pre>` : ""}<div class="detail-label">Remediation guidance</div><div class="detail-text">${esc(f.remediation || "No guidance recorded.")}</div>${["confirmed", "exploited"].includes(f.status) ? `<div class="report-actions"><button class="primary" data-prepare-fix="${esc(id)}" data-cid="${esc(cid)}">Prepare local fix →</button></div>` : ""}<div class="detail-label">Operator triage</div><div class="toolbar"><select id="triage-status">${["unconfirmed", "confirmed", "exploited", "false_positive", "accepted_risk", "remediated", "resolved"].map((x) => `<option value="${x}" ${f.status === x ? "selected" : ""}>${x.replaceAll("_", " ")}</option>`).join("")}</select><button class="secondary" data-triage="${esc(id)}" data-cid="${esc(cid)}">Save triage</button></div><small>Operator triage does not constitute a validated remediation retest.</small>`;
  $("#detail-body").insertAdjacentHTML("beforeend",
    `<div class="detail-label">Linked remediation records</div>${related ? (related.data.length ? related.data.map(r => `<div class="list-item"><div><strong>${esc(r.id)}</strong><small>${esc(r.record_type === "published_pr" ? "Published PR" : "Local proposal")} · ${esc(r.status || "unknown")}</small></div><button class="secondary" data-remediation="${esc(r.id)}" data-cid="${esc(cid)}" data-proposal-finding="${esc(id)}">Review</button></div>`).join("") : '<p class="instructions">No linked remediation records.</p>') : '<p class="instructions">Linked remediation records unavailable.</p>'}`);
  if (identity?.role === "admin") {
    $("#detail-body").insertAdjacentHTML("beforeend",
      `<button class="secondary" data-reveal-finding="${esc(id)}" data-cid="${esc(cid)}">Reveal recorded evidence (45-second grant)</button>`);
  }
  applyRoles();
  if (!$("#detail").open) $("#detail").showModal();
}
async function revealFinding(id, cid) {
  const request = findingDetailRequest, previousToken = token;
  const result = await grantedRequest("finding", id);
  if (request !== findingDetailRequest || currentFindingRef !== `${cid}:${id}` ||
      previousToken !== token || !$("#detail").open) return;
  const f = result.data;
  if (f.campaign_id !== cid || f.id !== id) throw new Error("Revealed resource identity mismatch");
  $("#detail-body [data-revealed-content]")?.remove();
  $("#detail-body").insertAdjacentHTML("beforeend",
    `<section data-revealed-content><h3>Authorized untrusted evidence</h3>${evidenceMarkup(f.evidence || f.evidence_output)}
      <pre>${esc(f.description || "")}</pre><pre>${esc(f.endpoint || "")}</pre>
      <pre>${esc(f.reproduction_steps || "")}</pre><pre>${esc(f.remediation || "")}</pre></section>`);
}
async function exportReport(cid, format) {
  if (identity?.role !== "admin") throw new Error("Administrator access required for full evidence exports");
  let body;
  if (format === "pdf") {
    const issued = await api("/api/v1/evidence/grants", {method:"POST",body:JSON.stringify({kind:"report_pdf",id:cid})});
    const res = await fetch(`/api/v1/campaigns/${encodeURIComponent(cid)}/report.pdf`, {
      headers: { Authorization: `Bearer ${token}`, "X-Darkmoon-Evidence-Grant": issued.grant }
    });
    if (!res.ok) throw new Error("Report export rejected");
    body = await res.blob();
  } else {
    const reveal = await grantedRequest(format === "json" ? "campaign" : "report", cid);
    body = new Blob([format === "json" ? JSON.stringify(reveal.data, null, 2) : reveal.data.content],
      {type: format === "json" ? "application/json" : "text/markdown"});
  }
  const url = URL.createObjectURL(body),
    a = document.createElement("a");
  a.href = url;
  a.download = `${cid}.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function loadRunQueue(signal) {
  const target = $("#run-queue");
  if (!target || signal?.aborted) return;
  runQueueControl?.abort();
  const controller = new AbortController();
  runQueueControl = controller;
  const abortForView = () => controller.abort();
  signal?.addEventListener("abort", abortForView, {once:true});
  const request = ++runQueueRequest;
  const offset = runQueueOffset;
  const activeOffset = runActiveOffset;
  try {
    const [active, recent] = await Promise.all([
      api(`/api/v1/run/active?limit=50&offset=${activeOffset}`, {signal:controller.signal}),
      api(`/api/v1/run/logs?limit=50&offset=${offset}`, {signal:controller.signal}),
    ]);
    if (controller.signal.aborted || request !== runQueueRequest || route !== "campaigns" || target !== $("#run-queue")) return;
    for (const [page, expectedOffset] of [[active, activeOffset], [recent, offset]]) {
      const end = expectedOffset + (Array.isArray(page?.data) ? page.data.length : 0);
      if (!page || !Array.isArray(page.data) || page.data.length > 50 ||
          page.limit !== 50 || page.offset !== expectedOffset ||
          !Number.isSafeInteger(page.total) || page.total < 0 ||
          (page.data.length > 0 && page.total < end) ||
          typeof page.has_more !== "boolean" || typeof page.paging_limit_reached !== "boolean" ||
          page.ordering !== "created_at_desc,id_desc" || page.page_consistency !== "live_offset" ||
          page.has_more !== (end < page.total && end <= 100000) ||
          page.paging_limit_reached !== (end < page.total && !page.has_more) ||
          (page.has_more ? page.next_offset !== end || end <= expectedOffset :
                           page.next_offset !== null) ||
          page.data.some(row => !row || typeof row.run_id !== "string" ||
            !row.run_id || row.run_id.length > 200 || typeof row.state !== "string" ||
            typeof row.status !== "string" ||
            !(row.campaign_id === null || typeof row.campaign_id === "string"))) {
        throw new Error("Run collection did not match the expected metadata contract");
      }
    }
    // Live queues can shrink while a previous page is selected. Rewind only
    // the affected pager, and preserve the other collection's position.
    const rewindActive = !active.data.length && activeOffset > 0 && active.total <= activeOffset;
    const rewindHistory = !recent.data.length && offset > 0 && recent.total <= offset;
    if (rewindActive || rewindHistory) {
      if (rewindActive) runActiveOffset = Math.max(0, Math.floor((active.total - 1) / 50) * 50);
      if (rewindHistory) runQueueOffset = Math.max(0, Math.floor((recent.total - 1) / 50) * 50);
      target.textContent = "Queue changed; recovering the last available page…";
      return loadRunQueue(signal);
    }
    const seen = new Set();
    const rows = [...active.data, ...recent.data].filter(row => {
      if (seen.has(row.run_id)) return false;
      seen.add(row.run_id);
      return true;
    });
    const notices = (!active.data.length && active.total ? "<p class='subtle'>No active records on this page.</p>" : "") +
      (!recent.data.length && recent.total ? "<p class='subtle'>No history records on this page.</p>" : "");
    target.innerHTML = (rows.length ? rows.map((j) => {
      const campaign = snapshot.campaigns.find((c) => c.id === j.campaign_id);
      const title = campaign?.name || j.run_id;
      const label = !j.log_status ? "Active run" : j.log_status === "unavailable" ? "Log unavailable" :
        j.log_status === "missing" ? "Log not yet created" : "Log metadata available";
      return `<div class="list-item"><div><a class="clickable" data-job="${esc(j.run_id)}">${esc(title)}</a><small>Run ${esc(j.run_id)} · Campaign ${esc(j.campaign_id || "unavailable")} · ${esc(date(j.created_at))} · ${esc(label)}</small></div><div>${badge(j.state)} ${["queued", "running", "cancelling"].includes(j.state) && identity?.role !== "viewer" ? `<button class="secondary" data-cancel="${esc(j.run_id)}">Cancel</button>` : ""}</div></div>`;
    }).join("") : empty(offset || activeOffset ? "No records on these pages" : "Queue is empty", offset || activeOffset ? "Use Previous to browse earlier records." : "No retained run records.")) +
      notices + `<div class="toolbar" aria-label="Active run pages"><button class="secondary" data-active-run-page="${Math.max(0, activeOffset - 50)}" ${activeOffset === 0 ? "disabled" : ""}>Previous active</button><span>Active ${active.data.length ? activeOffset + 1 : 0}–${active.data.length ? activeOffset + active.data.length : 0} of ${active.total}</span><button class="secondary" data-active-run-page="${active.next_offset ?? (activeOffset + 50)}" ${active.has_more ? "" : "disabled"}>Next active</button></div>` +
      `<div class="toolbar" aria-label="Run history pages"><button class="secondary" data-run-page="${Math.max(0, offset - 50)}" ${offset === 0 ? "disabled" : ""}>Previous</button><span>History ${recent.data.length ? offset + 1 : 0}–${recent.data.length ? offset + recent.data.length : 0} of ${recent.total}</span><button class="secondary" data-run-page="${recent.next_offset ?? (offset + 50)}" ${recent.has_more ? "" : "disabled"}>Next</button></div>` +
      `<p class="instructions">Pages reflect the current queue and may shift when runs are added or finish.${active.paging_limit_reached || recent.paging_limit_reached ? " The paging limit has been reached; use API history filters to narrow retained records." : ""}</p>`;
  } catch (error) {
    if (!controller.signal.aborted && request === runQueueRequest && route === "campaigns" && target === $("#run-queue"))
      target.textContent = "Run history unavailable: " + error.message;
  } finally {
    signal?.removeEventListener("abort", abortForView);
    if (runQueueControl === controller) runQueueControl = null;
  }
}
async function showJob(id) {
  const request = ++jobDetailRequest;
  currentDetailJob = id;
  $("#detail-title").textContent = "Run " + id;
  $("#detail-body").textContent = "Loading run and log metadata…";
  if (!$("#detail").open) $("#detail").showModal();
  try {
    const [j, log] = await Promise.all([
      api(`/api/v1/run/${encodeURIComponent(id)}`),
      api(`/api/v1/run/logs/${encodeURIComponent(id)}`),
    ]);
    if (request !== jobDetailRequest || currentDetailJob !== id || !$("#detail").open) return;
    $("#detail-title").textContent = "Run " + j.run_id;
    $("#detail-body").innerHTML = `${badge(j.state)}<p>Campaign: ${esc(j.campaign_id || "unavailable")}</p><p class="detail-text">Log: ${esc(log.log_status)}. Structured lifecycle messages only by default.</p><pre id="job-log"></pre>${identity?.role === "admin" && log.log_status === "available" ? `<button class="secondary" data-raw-job="${esc(id)}">Reveal untrusted raw output (may contain secrets)</button>` : ""}`;
    $("#job-log").textContent = log.data.map((row) => row.message).join("\n") || "No lifecycle messages available.";
    applyRoles();
  } catch (error) {
    if (request === jobDetailRequest && currentDetailJob === id && $("#detail").open)
      $("#detail-body").textContent = "Run details unavailable: " + error.message;
  }
}
async function launchDialog(schedule = false, record = null) {
  try {
    await window.populateLaunch();
  } catch (error) {
    fail(error);
    return;
  }
  scheduleMode = schedule;
  $("#launch-title").textContent = schedule
    ? "New recurring assessment"
    : "New assessment";
  $("#launch-submit").textContent = schedule
    ? "Create schedule →"
    : "Start assessment →";
  $("#schedule-fields").hidden = !schedule;
  window.ScheduleUI.configure(record);
  if (record) {$("#launch-title").textContent="Edit schedule";$("#launch-submit").textContent="Save schedule changes";}
  $("#launch-error").textContent = "";
  $("#launch-dialog").showModal();
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  token = $("#token").value;
  try {
    if ($("#login-username").value) {
      const result = await api("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: $("#login-username").value,
          password: token,
        }),
      });
      token = result.token;
    }
    await refresh();
    $("#token").value = "";
    $("#login").close();
    connect();
    if (identity?.authentication === "workspace-token") {
      api("/api/v1/auth/config").then(config => {
        if (!config.accounts_configured && token) $("#setup-account").showModal();
      }).catch(fail);
    }
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});
$("#setup-account-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget, submit = form.querySelector('[type="submit"]');
  $("#setup-account-error").textContent = "";
  if (form.elements.password.value !== form.elements.confirmation.value) {
    $("#setup-account-error").textContent = "Passwords do not match.";
    return;
  }
  submit.disabled = true;
  $("#setup-account-skip").disabled = true;
  let created = false;
  try {
    const result = await api("/api/v1/auth/setup", {method: "POST", body: JSON.stringify({username:form.elements.username.value, password:form.elements.password.value})});
    token = result.token;
    created = true;
    form.reset();
    $("#setup-account").close();
    location.hash = "settings";
    await refresh();
    connect();
  } catch (error) {
    if (created) fail(error);
    else $("#setup-account-error").textContent = error.message;
  } finally {submit.disabled = false; $("#setup-account-skip").disabled = false;}
});
$("#setup-account").addEventListener("cancel", event => {
  if ($("#setup-account-form [type=submit]").disabled) event.preventDefault();
});
$("#setup-account-skip").addEventListener("click", () => $("#setup-account").close());
$("#setup-account").addEventListener("close", () => $("#setup-account-form").reset());
$("#login").addEventListener("cancel", (e) => e.preventDefault());
$("#detail").addEventListener("close", () => {
  currentDetailJob = "";
  currentFindingRef = "";
  clearRevealedContent();
  $("#detail-body").replaceChildren();
  jobDetailRequest++;
});
$("#logout").addEventListener("click", async () => {
  try {
    await api("/api/v1/auth/logout", { method: "POST", body: "{}" });
  } finally {
    lock();
  }
});
$("#new-campaign").addEventListener("click", () => launchDialog());
$("#launch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = $("#launch-submit");
  button.disabled = true;
  try {
    const values = window.launchValues(e.target);
    values.remediate = e.target.elements.remediate.checked;
    if (scheduleMode) {
      const record = window.ScheduleUI.editing(), payload = window.ScheduleUI.payload();
      await api(`/api/v1/schedules${record?"/"+encodeURIComponent(record.id):""}`, {
        method:record?"PATCH":"POST", body:JSON.stringify(record?{...payload,version:record.version||1}:payload),
      });
    } else {
      await api("/api/v1/campaigns", {method:"POST",body:JSON.stringify(values),headers:{"Idempotency-Key":crypto.randomUUID()}});
    }
    $("#launch-dialog").close();
    location.hash = scheduleMode ? "schedules" : "campaigns";
    await refresh();
  } catch (err) {
    $("#launch-error").textContent = err.message;
  } finally {
    button.disabled = false;
  }
});
document.addEventListener("click", async (e) => {
  if (e.target.closest('nav a[href="#findings"]') && lastFindingsHash) {
    e.preventDefault();
    if (location.hash !== lastFindingsHash) location.hash = lastFindingsHash;
  }
  const b = e.target.closest(
    "button,[data-campaign],[data-finding],[data-job],[data-remediation]",
  );
  if (!b) return;
  try {
    if (b.dataset.activeRunPage !== undefined) {
      const next = Number(b.dataset.activeRunPage);
      if (!Number.isSafeInteger(next) || next < 0 || next > 100000) return;
      runActiveOffset = next;
      if ($("#run-queue")) $("#run-queue").textContent = "Loading runs…";
      loadRunQueue(viewControl.signal);
    } else if (b.dataset.runPage !== undefined) {
      const next = Number(b.dataset.runPage);
      if (!Number.isSafeInteger(next) || next < 0 || next > 100000) return;
      runQueueOffset = next;
      if ($("#run-queue")) $("#run-queue").textContent = "Loading runs…";
      loadRunQueue(viewControl.signal);
    } else if (b.dataset.findingsPage) {
      updateFindingView({page:Number(b.dataset.findingsPage)}, true);
      $("#finding-count").setAttribute("tabindex", "-1");
      $("#finding-count").focus();
    } else if (b.id === "findings-clear") {
      updateFindingView({...Object.fromEntries(FindingQuery.filters.map(k=>[k,""])),q:"",triage:"",sort:"severity_desc",size:50,page:1}, true);
    } else if (b.classList.contains("close-dialog")) {
      b.closest("dialog").close();
      currentDetailJob = "";
    } else if (b.dataset.campaign) await showCampaign(b.dataset.campaign);
    else if (b.dataset.finding)
      await showFinding(b.dataset.finding, b.dataset.cid);
    else if (b.dataset.revealFinding)
      await revealFinding(b.dataset.revealFinding, b.dataset.cid);
    else if (b.dataset.export)
      await exportReport(b.dataset.cid, b.dataset.export);
    else if (b.dataset.patch) {
      const result = await grantedRequest("patch", b.dataset.patch);
      const url = URL.createObjectURL(new Blob([result.data.patch], {type:"text/x-diff"})),
        a = document.createElement("a");
      a.href = url;
      a.download = b.dataset.patch + ".patch";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else if (b.dataset.rawJob) {
      const id = b.dataset.rawJob;
      const request = jobDetailRequest;
      if (identity?.role !== "admin") return;
      const output = $("#job-log");
      jobRevealPending = true;
      if (output) output.textContent = "Loading untrusted output…";
      try {
        const log = await grantedRequest("run", id,
          `/api/v1/run/logs/${encodeURIComponent(id)}?raw=true&lines=100`);
        if (request === jobDetailRequest && currentDetailJob === id && $("#detail").open && $("#job-log")) {
          $("#job-log").textContent = log.data.map((row) => row.message).join("\n") || "No raw lines in the bounded window.";
          if (log.truncated) $("#job-log").textContent += "\n[output window truncated]";
          $("#job-log").dataset.revealedContent = "true";
          jobRevealUntil = Date.now() + 45000;
        }
      } catch (error) {
        if (request === jobDetailRequest && currentDetailJob === id && $("#detail").open && $("#job-log")) $("#job-log").textContent = "Log unavailable: " + error.message;
      } finally {
        jobRevealPending = false;
      }
    } else if (b.dataset.job) await showJob(b.dataset.job);
    else if (b.dataset.cancel) {
      await api(`/api/v1/run/${encodeURIComponent(b.dataset.cancel)}/stop`, {
        method: "DELETE",
      });
      await refresh();
    } else if (b.id === "new-schedule") launchDialog(true);
    else if (b.dataset.editSchedule) {
      await launchDialog(true, snapshot.schedules.find(s=>s.id===b.dataset.editSchedule));
    } else if (b.dataset.duplicateSchedule) {
      const item=snapshot.schedules.find(s=>s.id===b.dataset.duplicateSchedule);
      await api(`/api/v1/schedules/${encodeURIComponent(item.id)}/duplicate`,{method:"POST",body:JSON.stringify({version:item.version||1})});
      await refresh();
    } else if (b.dataset.scheduleHistory) {
      const item=snapshot.schedules.find(s=>s.id===b.dataset.scheduleHistory);
      const result=await api(`/api/v1/schedules/${encodeURIComponent(item.id)}/history`);
      currentDetailJob="";
      $("#detail-title").textContent="Schedule history · "+(item.display_name||item.spec.name);
      $("#detail-body").innerHTML=result.data.length?result.data.map(h=>`<section class="panel"><p>Due ${esc(date(h.due_at))}</p>${badge(h.disposition)} ${h.job_status?badge(h.job_status):""}<p>${esc(h.error||"")}</p>${h.job_id?`<button class="secondary" data-job="${esc(h.job_id)}">View job</button>`:""}${h.campaign_id?`<button class="secondary" data-campaign="${esc(h.campaign_id)}">View campaign</button>`:""}</section>`).join(""):empty("No run history yet","Up to 100 claimed occurrences are retained for each schedule.");
      $("#detail").showModal();
    } else if (b.id === "open-map") {
      $("#detail").close();
      location.hash = "surface";
    } else if (b.dataset.toggleSchedule) {
      const s = snapshot.schedules.find(
        (x) => x.id === b.dataset.toggleSchedule,
      );
      await api(`/api/v1/schedules/${s.id}`, {
        method: "PATCH",
        body: JSON.stringify({ version:s.version||1, enabled: !s.enabled }),
      });
      await refresh();
    } else if (b.dataset.deleteSchedule) {
      await api(`/api/v1/schedules/${b.dataset.deleteSchedule}`, {
        method: "DELETE",
      });
      await refresh();
    } else if (b.dataset.prepareFix) {
      await window.populateRemediation();
      const form = $("#remediation-form");
      form.elements.campaign_id.value = b.dataset.cid;
      form.elements.finding_id.value = b.dataset.prepareFix;
      $("#remediation-error").textContent = "";
      $("#detail").close();
      $("#remediation-dialog").showModal();
    } else if (b.dataset.triage) {
      await api(
        `/api/v1/campaigns/${b.dataset.cid}/findings/${b.dataset.triage}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: $("#triage-status").value }),
        },
      );
      await showFinding(b.dataset.triage, b.dataset.cid);
      await refresh();
    } else if (b.dataset.remediation) {
      const records = await api("/api/v1/remediations");
      const r = records.find(x => x.id === b.dataset.remediation);
      if (!r || (b.dataset.cid && r.campaign_id !== b.dataset.cid) ||
          (b.dataset.proposalFinding && r.finding_id !== b.dataset.proposalFinding))
        throw new Error("Proposal is unavailable for this finding and campaign");
      $("#detail-title").textContent = r.title || r.id;
      $("#detail-body").innerHTML =
        `${badge(r.status)} ${identity?.role === "admin" ? `<button class="secondary" data-patch="${esc(r.id)}">Download patch with authorization</button>` : ""}<pre>${esc(JSON.stringify(r, null, 2))}</pre>`;
      $("#detail").showModal();
    }
  } catch (err) {
    fail(err);
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "campaign-select") {
    campaignId = e.target.value;
    render();
  }
  const key = e.target.dataset.findingFilter || ({"finding-sort":"sort","finding-size":"size"})[e.target.id];
  if (key) {
    const id = e.target.id, value = key === "size" ? Number(e.target.value) : e.target.value;
    updateFindingView({[key]:value,page:1}, true);
    $("#" + id).focus();
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "finding-search") {
    const pos = e.target.selectionStart;
    updateFindingView({q:e.target.value,page:1});
    $("#finding-search").focus();
    $("#finding-search").setSelectionRange(pos, pos);
  }
});
$("#remediation-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target,
    button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const values = {
      campaign_id: form.elements.campaign_id.value,
      finding_id: form.elements.finding_id.value,
      repo: form.elements.repo.value,
      generate: form.elements.generate.checked,
      validate: form.elements.validate.checked,
      files: form.elements.files.value
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean),
    };
    if (!values.generate) values.edits = JSON.parse(form.elements.edits.value);
    await api("/api/v1/remediations", {
      method: "POST",
      body: JSON.stringify(values),
    });
    $("#remediation-dialog").close();
    location.hash = "remediation";
    await refresh();
  } catch (err) {
    $("#remediation-error").textContent = err.message;
  } finally {
    button.disabled = false;
  }
});
window.addEventListener("hashchange", render);
setInterval(() => {
  if (jobRevealPending) return;
  if (jobRevealUntil && Date.now() < jobRevealUntil) return;
  if (jobRevealUntil) {
    jobRevealUntil = 0;
    const log = $("#job-log");
    if (log) {
      log.textContent = "Raw output authorization expired.";
      delete log.dataset.revealedContent;
    }
  }
  if (currentDetailJob && $("#detail").open)
    showJob(currentDetailJob).catch(fail);
}, 2000);

async function drawSurface(cid, signal) {
  const [graph, proposalResult] = await Promise.all([
    api(`/api/v1/campaigns/${encodeURIComponent(cid)}/graph`),
    api(`/api/v1/pull-requests?campaign_id=${encodeURIComponent(cid)}`).catch(() => null),
  ]);
  const proposals = (proposalResult?.data || []).filter(p => p.campaign_id === cid);
  let inspectorVersion = 0;
  if (signal.aborted) return;
  const canvas = $("#surface-canvas"),
    ctx = canvas.getContext("2d"),
    info = $("#map-info");
  const nodes = graph.nodes.map((n, i) => {
    const t = (i / Math.max(1, graph.nodes.length)) * Math.PI * 2,
      tier = ["database", "data", "secrets", "secret"].includes(n.node_type)
        ? 3
        : ["service", "port"].includes(n.node_type)
          ? 1
          : ["target", "host"].includes(n.node_type)
            ? 0
            : 2,
      r = [2.2, 1.7, 1.2, 0.65][tier],
      linked = graph.findings.filter(
        (f) => f.node_id === n.id || f.infra_node_id === n.id,
      ),
      risk = ["critical", "high", "medium", "low", "info"].find((sev) =>
        linked.some((f) => f.severity === sev),
      );
    return {
      ...n,
      linked,
      risk,
      p: [Math.cos(t) * r, Math.sin(t) * r, ((i % 3) - 1) * 0.9],
    };
  });
  const ids = new Map(nodes.map((n) => [n.id, n]));
  let angle = 0.4,
    tilt = 0.3,
    zoom = 1,
    drag = null,
    selected = "",
    frame, pathController = null, highlightedEdge = "";
  info.innerHTML = `<h3>${nodes.length} infrastructure nodes</h3><p class="instructions">${graph.edges.length} recorded relationships · ${graph.findings.length} findings</p><p class="instructions">Select a node to inspect its metadata and explicitly linked findings. This map does not infer an exploitation path.</p>`;
  if (!nodes.length)
    info.innerHTML = empty(
      "No infrastructure recorded",
      "Nodes appear as agents map the target.",
    );
  function draw() {
    const rect = canvas.getBoundingClientRect(),
      dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const w = rect.width,
      h = rect.height;
    ctx.fillStyle = "#0b111b";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#1b2638";
    for (let i = 1; i < 5; i++) {
      ctx.beginPath();
      ctx.ellipse(w / 2, h / 2, (i * w) / 11, (i * h) / 13, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
    for (const n of nodes) {
      const [x, y, z] = n.p,
        rx = x * Math.cos(angle) - z * Math.sin(angle),
        rz = x * Math.sin(angle) + z * Math.cos(angle),
        ry = y * Math.cos(tilt) - rz * Math.sin(tilt);
      n.screen = [w / 2 + rx * w * 0.14 * zoom, h / 2 + ry * h * 0.18 * zoom];
      n.depth = rz;
    }
    for (const e of graph.edges) {
      const a = ids.get(e.source),
        b = ids.get(e.target);
      if (!a || !b) continue;
      ctx.strokeStyle = e.id === highlightedEdge ? "#b2f4cd" : e.kind === "observed" ? "#9f93df" : "#3a5067";
      ctx.lineWidth = e.id === highlightedEdge ? 4 : 1;
      ctx.beginPath();
      ctx.moveTo(...a.screen);
      ctx.lineTo(...b.screen);
      ctx.stroke();
    }
    for (const n of [...nodes].sort((a, b) => a.depth - b.depth)) {
      const [x, y] = n.screen,
        r = n.node_type === "target" ? 10 : 6;
      ctx.fillStyle =
        n.id === selected
          ? "#ffffff"
          : severityColors[n.risk] ||
            (n.node_type === "target" ? "#b2f4cd" : "#a69ce2");
      ctx.shadowColor = ctx.fillStyle;
      ctx.shadowBlur = 14;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#afbed2";
      ctx.font = "10px system-ui";
      ctx.textAlign = x > w * 0.6 ? "right" : "left";
      ctx.fillText(
        String(n.label || n.title || n.id).slice(0, 30) +
          (n.linked.length ? ` · ${n.linked.length} findings` : ""),
        x + (x > w * 0.6 ? -r - 6 : r + 6),
        y + 3,
      );
      ctx.textAlign = "left";
    }
    frame = requestAnimationFrame(draw);
  }
  canvas.addEventListener(
    "pointerdown",
    (e) => {
      drag = [e.clientX, e.clientY];
      canvas.setPointerCapture(e.pointerId);
    },
    { signal },
  );
  canvas.addEventListener(
    "pointermove",
    (e) => {
      if (drag) {
        angle += (e.clientX - drag[0]) * 0.008;
        tilt += (e.clientY - drag[1]) * 0.008;
        drag = [e.clientX, e.clientY];
      }
    },
    { signal },
  );
  canvas.addEventListener(
    "pointerup",
    () => {
      drag = null;
    },
    { signal },
  );
  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      zoom = Math.min(3, Math.max(0.4, zoom - e.deltaY * 0.001));
    },
    { passive: false, signal },
  );
  canvas.addEventListener(
    "click",
    (e) => {
      const r = canvas.getBoundingClientRect(),
        n = nodes.find(
          (n) =>
            Math.hypot(
              n.screen[0] - (e.clientX - r.left),
              n.screen[1] - (e.clientY - r.top),
            ) < 16,
        );
      if (!n) return;
      selectNode(n);
    },
    { signal },
  );
  const controls = $("#surface-controls"),
    card = $("#surface-tour-card"),
    tour = $("#surface-tour"),
    locations = nodes.filter((n) => n.linked.length);
  let tourIndex = 0;
  controls.innerHTML = `<label for="surface-node">Inspect infrastructure</label><select id="surface-node"><option value="">Choose an asset</option>${nodes.map(n => `<option value="${esc(n.id)}">${esc(n.label || n.id)} (${n.linked.length} findings)</option>`).join("")}</select>`;
  const picker = $("#surface-node");
  picker.disabled = !nodes.length;
  picker.addEventListener("change", () => {
    const n = ids.get(picker.value);
    if (n) selectNode(n);
    else clearInspector();
  }, { signal });
  function clearInspector() {
    inspectorVersion++;
    if (!card.hidden) stopTour(false);
    selected = "";
    info.classList.remove("has-selection");
    picker.value = "";
    info.innerHTML = `<p class="instructions">Select an asset to inspect its metadata and linked findings.</p>`;
    picker.focus();
  }
  function selectNode(n, fromTour = false) {
    if (!fromTour && !card.hidden) stopTour(false);
    inspectorVersion++;
    info.classList.add("has-selection");
    selected = n.id;
    picker.value = n.id;
    const metadata = Object.fromEntries(Object.entries(n).filter(([k]) => !["p", "screen", "depth", "linked", "risk"].includes(k)));
    const severityOrder = ["critical", "high", "medium", "low", "info"];
    const totals = severityOrder.map(severity => ({severity, count: n.linked.filter(f => f.severity === severity).length})).filter(item => item.count);
    const fields = [["Type", n.node_type], ["Address", n.ip_address || n.ip || n.address], ["Endpoint", n.endpoint || n.url], ["Technology", n.technology || n.service || n.os]];
    const summary = fields.filter(([, value]) => value !== undefined && value !== null && value !== "").map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(typeof value === "object" ? JSON.stringify(value) : value)}</dd></div>`).join("");
    info.innerHTML = `<button class="secondary" id="surface-close">Close inspector</button><h3>${esc(n.label || n.id)}</h3><dl class="asset-fields">${summary}</dl><div class="asset-severities" aria-label="Linked findings by severity">${totals.map(item => `<span>${badge(item.severity)} ${item.count}</span>`).join("")}</div><details><summary>Asset metadata</summary><pre>${esc(JSON.stringify(metadata, null, 2))}</pre></details><h3>${n.linked.length} explicitly linked findings</h3>${n.linked.length ? n.linked.map(f => `<button class="list-item" data-surface-finding="${esc(f.id)}">${badge(f.severity)} ${proposals.some(p => (p.finding_ids || []).includes(f.id)) ? '<span class="badge">Proposal recorded</span>' : ""}<span class="finding-score">CVSS ${esc(f.cvss_score ?? "—")}</span><strong>${esc(f.title || "Untitled finding")}</strong><small>${esc([f.category, f.status].filter(Boolean).join(" · "))}</small><small>${esc([f.mitre_attack_id, f.mitre_attack_name].filter(Boolean).join(" · "))}</small></button>`).join("") : empty("No linked findings", "No findings are explicitly linked to this asset.")}`;
    $("#surface-close").addEventListener("click", clearInspector, { signal });
  }
  info.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-surface-finding]");
    if (!button) return;
    const n = ids.get(selected), findingId = button.dataset.surfaceFinding;
    if (!n || !n.linked.some(f => f.id === findingId)) return;
    if (!card.hidden) stopTour(false);
    const version = ++inspectorVersion;
    info.innerHTML = '<button class="secondary" id="surface-loading-back">Back to asset</button><p role="status">Loading finding…</p>';
    $("#surface-loading-back").addEventListener("click", () => {selectNode(n); picker.focus();}, {signal});
    try {
      const campaign = await api(`/api/v1/campaigns/${encodeURIComponent(cid)}`);
      if (signal.aborted || version !== inspectorVersion) return;
      const f = campaign.findings.find(f => f.id === findingId && (f.node_id === n.id || f.infra_node_id === n.id));
      const related = proposals.filter(p => (p.finding_ids || []).includes(findingId));
      info.innerHTML = `<button class="secondary" id="surface-back">← Back to ${esc(n.label || n.id)}</button>${f ? `<h3 id="surface-finding-title" tabindex="-1">${esc(f.title || f.id)}</h3>${badge(f.severity)} ${badge(f.status)}<p>CVSS ${esc(f.cvss_score ?? "—")}</p>${[["Endpoint", f.endpoint], ["MITRE ATT&CK", [f.mitre_attack_id, f.mitre_attack_name].filter(Boolean).join(" · ")], ["Description", f.description], ["Remediation", f.remediation]].filter(([, value]) => value).map(([label, value]) => `<h4>${esc(label)}</h4><p class="detail-text">${esc(value)}</p>`).join("")}<h4>Proposals</h4>${related.length ? related.map(p => `<button class="secondary" data-remediation="${esc(p.id)}" data-cid="${esc(cid)}" data-proposal-finding="${esc(f.id)}">Review ${esc(p.title || p.id)} · ${esc(p.status || "unknown")}</button>`).join("") : `<p class="instructions">${proposalResult ? "No proposal recorded for this finding." : "Proposal records could not be loaded. Reopen the graph to retry."}</p>`}<div class="report-actions"><button class="secondary" data-finding="${esc(f.id)}" data-cid="${esc(cid)}">Full finding and evidence</button><button class="secondary" data-report-preview="${esc(cid)}">Campaign report</button></div>` : empty("Finding unavailable", "It was removed or is no longer linked to this asset. Return to the asset list.")}`;
      $("#surface-back").addEventListener("click", () => {
        selectNode(n);
        const row = Array.from(info.querySelectorAll("[data-surface-finding]")).find(b => b.dataset.surfaceFinding === findingId);
        (row || picker).focus();
      }, {signal});
      ($("#surface-finding-title") || $("#surface-back")).focus();
    } catch (error) {
      if (signal.aborted || version !== inspectorVersion) return;
      info.innerHTML = '<button class="secondary" id="surface-back">Back to asset</button><p role="status">Finding could not be loaded. Return to the asset and try again.</p>';
      $("#surface-back").addEventListener("click", () => { selectNode(n); picker.focus(); }, {signal});
      $("#surface-back").focus();
    }
  }, {signal});
  function stopTour(restoreFocus = true) {
    pathController?.stop(false);
    card.hidden = true;
    tour.textContent = "Tour finding locations";
    if (restoreFocus) tour.focus();
  }
  function showStep() {
    const n = locations[tourIndex];
    selectNode(n, true);
    card.hidden = false;
    // Manual steps reframe instantly; no timed motion or automatic advance.
    angle = -Math.atan2(n.p[2], n.p[0]) + 0.25;
    card.innerHTML = `<p role="status">Step ${tourIndex + 1} of ${locations.length} · ${esc(n.label || n.id)}</p><p class="instructions">Finding locations, not an exploitation chain. Each step selects an asset with explicitly linked findings.</p><div class="toolbar"><button class="secondary" id="surface-prev" ${tourIndex === 0 ? "disabled" : ""}>Back</button><button class="secondary" id="surface-next" >${tourIndex === locations.length - 1 ? "Finish" : "Next"}</button><button class="secondary" id="surface-free">Explore freely</button></div>`;
    for (const [id, delta] of [["#surface-prev", -1], ["#surface-next", 1]]) {
      $(id).addEventListener("click", () => {
        if (delta === 1 && tourIndex === locations.length - 1) return stopTour();
        tourIndex = Math.max(0, Math.min(locations.length - 1, tourIndex + delta));
        showStep();
        const preferred = $(id);
        (preferred.disabled ? $("#surface-free") : preferred).focus();
      }, { signal });
    }
    $("#surface-free").addEventListener("click", () => stopTour(), { signal });
  }
  tour.disabled = !locations.length;
  tour.addEventListener("click", () => {
    if (!card.hidden) return stopTour();
    tourIndex = 0;
    tour.textContent = "Stop tour";
    showStep();
    $("#surface-free").focus();
  }, { signal });
  if (window.setupRecordedPaths && $("#recorded-paths")) {
    pathController = window.setupRecordedPaths({graph, cid, signal, card,
      stopLocationTour: () => stopTour(false),
      highlight: edgeId => { highlightedEdge = edgeId; },
      selectStep: edge => {
        const node = ids.get(edge.target);
        if (!node) throw new Error("Graph changed; reopen this assessment's surface");
        selectNode(node, true);
        angle = -Math.atan2(node.p[2], node.p[0]) + 0.25;
      },
    });
  }
  signal.addEventListener("abort", () => cancelAnimationFrame(frame), { once: true });
  draw();
  const vr = $("#vr-button");
  if (navigator.xr && (await navigator.xr.isSessionSupported("immersive-vr"))) {
    if (signal.aborted) return;
    vr.disabled = false;
    vr.textContent = "Enter VR";
    vr.addEventListener(
      "click",
      () => startVR(nodes, graph.edges).catch(fail),
      { signal },
    );
  } else {
    vr.textContent = "VR unavailable";
  }
}
async function startVR(nodes, edges) {
  const canvas = document.createElement("canvas"),
    gl = canvas.getContext("webgl", { xrCompatible: true });
  if (!gl) throw new Error("WebGL is unavailable");
  const session = await navigator.xr.requestSession("immersive-vr");
  try {
    await gl.makeXRCompatible();
    session.updateRenderState({ baseLayer: new XRWebGLLayer(session, gl) });
    const space = await session.requestReferenceSpace("local");
    function shader(type, source) {
      const s = gl.createShader(type);
      gl.shaderSource(s, source);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
        throw new Error(gl.getShaderInfoLog(s));
      return s;
    }
    const program = gl.createProgram();
    gl.attachShader(
      program,
      shader(
        gl.VERTEX_SHADER,
        "attribute vec3 p;uniform mat4 projection;uniform mat4 view;void main(){gl_Position=projection*view*vec4(p.x,p.y+1.4,p.z-5.0,1.0);gl_PointSize=14.0;}",
      ),
    );
    gl.attachShader(
      program,
      shader(
        gl.FRAGMENT_SHADER,
        "precision mediump float;uniform vec4 color;void main(){gl_FragColor=color;}",
      ),
    );
    gl.linkProgram(program);
    gl.useProgram(program);
    const lookup = new Map(nodes.map((n) => [n.id, n.p])),
      linePoints = edges.flatMap((e) =>
        lookup.has(e.source) && lookup.has(e.target)
          ? [...lookup.get(e.source), ...lookup.get(e.target)]
          : [],
      ),
      points = nodes.flatMap((n) => n.p);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([...linePoints, ...points]),
      gl.STATIC_DRAW,
    );
    const p = gl.getAttribLocation(program, "p");
    gl.enableVertexAttribArray(p);
    gl.vertexAttribPointer(p, 3, gl.FLOAT, false, 0, 0);
    function frame(t, f) {
      const pose = f.getViewerPose(space);
      if (pose) {
        gl.bindFramebuffer(
          gl.FRAMEBUFFER,
          session.renderState.baseLayer.framebuffer,
        );
        gl.clearColor(0.03, 0.05, 0.08, 1);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
        for (const v of pose.views) {
          const port = session.renderState.baseLayer.getViewport(v);
          gl.viewport(port.x, port.y, port.width, port.height);
          gl.uniformMatrix4fv(
            gl.getUniformLocation(program, "projection"),
            false,
            v.projectionMatrix,
          );
          gl.uniformMatrix4fv(
            gl.getUniformLocation(program, "view"),
            false,
            v.transform.inverse.matrix,
          );
          gl.uniform4f(
            gl.getUniformLocation(program, "color"),
            0.35,
            0.42,
            0.6,
            1,
          );
          gl.drawArrays(gl.LINES, 0, linePoints.length / 3);
          gl.uniform4f(
            gl.getUniformLocation(program, "color"),
            0.65,
            0.94,
            0.76,
            1,
          );
          gl.drawArrays(gl.POINTS, linePoints.length / 3, points.length / 3);
        }
      }
      session.requestAnimationFrame(frame);
    }
    session.addEventListener(
      "end",
      () => {
        gl.deleteBuffer(buffer);
        gl.deleteProgram(program);
      },
      { once: true },
    );
    session.requestAnimationFrame(frame);
  } catch (e) {
    await session.end();
    throw e;
  }
}
lock();
