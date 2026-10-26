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
let token = "",
  snapshot = null,
  campaignId = "",
  route = "overview",
  streamControl,
  viewControl,
  scheduleMode = false;
let selectedSeverity = "",
  selectedSearch = "",
  currentDetailJob = "";
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
  token = "";
  snapshot = null;
  streamControl?.abort();
  $("#login").showModal();
  $("#content").replaceChildren();
}
async function refresh() {
  snapshot = await api("/api/v1/overview");
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
  return `<div class="table-scroll"><table><thead><tr><th>SEVERITY</th><th>FINDING / ENDPOINT</th><th>CVSS</th><th>STATUS</th><th>MITRE ATT&CK</th></tr></thead><tbody>${items.map((f) => `<tr class="clickable" data-finding="${esc(f.id)}" data-cid="${esc(f.campaign_id)}"><td>${badge(f.severity || "info")}</td><td>${esc(f.title || "Untitled")}<small>${esc(f.endpoint || f.category || "")}</small></td><td>${esc(f.cvss_score ?? "—")}</td><td>${badge(f.status)}</td><td>${esc(f.mitre_attack_id || "—")}</td></tr>`).join("")}</tbody></table></div>`;
}
function render() {
  if (!snapshot) return;
  viewControl?.abort();
  viewControl = new AbortController();
  route = location.hash.slice(1) || "overview";
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
  $("#heading").textContent = headings[route];
  document
    .querySelectorAll("nav a")
    .forEach((a) => a.classList.toggle("active", a.hash === `#${route}`));
  const s = snapshot,
    total = s.findings.length;
  if (route === "overview") {
    $("#content").innerHTML =
      `<div class="section-top"><div><h2>Your security workspace</h2><p>Assessments, evidence and remediation in one place.</p></div><span class="subtle">${esc(new Date().toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }))}</span></div><div class="cards"><div class="card"><div class="label">Assessments</div><div class="number">${s.campaigns.length}</div><div class="note">${s.campaigns.filter((c) => c.status === "running").length} in progress</div></div><div class="card"><div class="label">Total findings</div><div class="number">${total}</div><div class="note">Across ${s.targets.length} targets</div></div><div class="card"><div class="label">Critical + high</div><div class="number critical-text">${s.stats.critical + s.stats.high}</div><div class="note">Prioritize review and remediation</div></div><div class="card"><div class="label">Confirmed / exploited</div><div class="number accent">${s.findings.filter((f) => ["confirmed", "exploited"].includes(f.status)).length}</div><div class="note">Backed by recorded agent evidence</div></div></div><div class="grid"><section class="panel flush"><div class="section-top"><h3>Recent assessments</h3><a class="subtle" href="#campaigns">View all →</a></div>${campaignsTable(s.campaigns.slice(-6))}</section><section class="panel"><div class="section-top"><h3>Finding distribution</h3><span class="subtle">${total} total</span></div>${Object.entries(
        s.stats,
      )
        .map(
          ([sev, n]) =>
            `<div class="severity-row"><span>${esc(sev)}</span><div class="severity-track"><canvas data-sev="${sev}" data-share="${total ? n / total : 0}" width="500" height="5"></canvas></div><span class="severity-count">${n}</span></div>`,
        )
        .join("")}<hr class="divider"><h3>Projects & targets</h3>${
        s.projects
          .slice(-5)
          .map(
            (p) =>
              `<div class="list-item"><div>${esc(p.name)}<small>${esc(s.targets.find((t) => t.id === p.target_id)?.host || p.description)}</small></div>${badge(s.targets.find((t) => t.id === p.target_id)?.risk_level || "none")}</div>`,
          )
          .join("") || empty("No projects yet")
      }</section></div>`;
    document.querySelectorAll("[data-sev]").forEach((c) => {
      const ctx = c.getContext("2d");
      ctx.fillStyle = severityColors[c.dataset.sev];
      ctx.fillRect(0, 0, 500 * Number(c.dataset.share), 5);
    });
  } else if (route === "campaigns") {
    $("#content").innerHTML =
      `<section class="panel flush"><div class="section-top"><div><h3>All assessments</h3><p>Select one to review its findings, report and infrastructure.</p></div></div>${campaignsTable(s.campaigns)}</section><section class="panel"><div class="section-top"><h3>Execution queue</h3><span class="subtle">One assessment at a time</span></div>${
        s.jobs.length
          ? s.jobs
              .slice()
              .reverse()
              .map(
                (j) =>
                  `<div class="list-item"><div><a class="clickable" data-job="${esc(j.id)}">${esc(j.spec.name)}</a><small>${esc(j.spec.target)} · ${esc(date(j.created_at))}</small></div><div>${badge(j.status)} ${["queued", "running"].includes(j.status) ? `<button class="secondary" data-cancel="${esc(j.id)}">Cancel</button>` : ""}</div></div>`,
              )
              .join("")
          : empty("Queue is empty")
      }</section>`;
  } else if (route === "findings") {
    const items = s.findings.filter(
      (f) =>
        (!selectedSeverity || f.severity === selectedSeverity) &&
        (!selectedSearch ||
          `${f.title} ${f.endpoint} ${f.category}`
            .toLowerCase()
            .includes(selectedSearch.toLowerCase())),
    );
    $("#content").innerHTML =
      `<div class="toolbar"><input id="finding-search" aria-label="Search findings" placeholder="Search findings or endpoints…" value="${esc(selectedSearch)}"><select id="severity-filter" aria-label="Severity"><option value="">All severities</option>${Object.keys(
        severityColors,
      )
        .map(
          (x) =>
            `<option ${selectedSeverity === x ? "selected" : ""}>${x}</option>`,
        )
        .join(
          "",
        )}</select><span class="subtle">${items.length} findings</span></div><section class="panel flush">${findingsTable(items)}</section>`;
  } else if (route === "surface") {
    $("#content").innerHTML =
      `<div class="toolbar">${campaignSelect()}<button class="secondary" id="vr-button" disabled>Checking VR…</button><button class="secondary" id="surface-tour">Tour finding locations</button></div><div class="panel"><div class="map-layout"><div><canvas id="surface-canvas" class="surface" aria-label="Interactive three dimensional infrastructure graph"></canvas><p class="map-caption">Drag to orbit · Scroll to zoom · Select a node to inspect. Lines show recorded containment and connections.</p></div><div class="map-info" id="map-info">Choose an assessment to explore its infrastructure.</div></div></div>`;
    if (campaignId) drawSurface(campaignId, viewControl.signal).catch(fail);
  } else if (route === "schedules") {
    $("#content").innerHTML =
      `<section class="panel"><div class="section-top"><div><h3>Recurring assessments</h3><p>Times use your browser timezone. Missed occurrences run once after restart; overlapping runs are skipped.</p></div><button class="primary" id="new-schedule">+ Add schedule</button></div>${s.schedules.length ? `<div class="table-scroll"><table><thead><tr><th>ASSESSMENT / TARGET</th><th>INTERVAL</th><th>NEXT RUN</th><th>LAST RESULT</th><th>ACTIONS</th></tr></thead><tbody>${s.schedules.map((x) => `<tr><td>${esc(x.spec.name)}<small>${esc(x.spec.target)}</small></td><td>${+(x.interval_seconds / 3600).toFixed(2)} hours</td><td>${esc(date(x.next_run))}<small>${x.enabled ? "Enabled" : "Paused"}</small></td><td>${esc(x.last_disposition || "Not run")}<small>${esc(x.last_error || "")}</small></td><td><button class="secondary" data-toggle-schedule="${esc(x.id)}">${x.enabled ? "Pause" : "Resume"}</button> <button class="secondary" data-delete-schedule="${esc(x.id)}">Delete</button></td></tr>`).join("")}</tbody></table></div>` : empty("No scheduled assessments", "Create a recurring assessment with the same scope controls as a manual run.")}</section>`;
  } else if (route === "remediation") {
    $("#content").innerHTML =
      `<section class="panel"><div class="section-top"><div><h3>Local remediation proposals</h3><p>Patches and validation evidence, prepared for your review.</p></div><span class="badge">Publishing disabled</span></div><p class="instructions">Use the remediation command with a local source repository and a confirmed finding. It creates an isolated Git worktree, applies structured edits, and can run before/after regression probes in disposable Docker containers. Add <code>--generate</code> to use your configured model. No branch is pushed and no PR is opened.</p><pre>PYTHONPATH=mcp python3 -m community.remediation \
  --repo /path/to/target-source --campaign-id CAMPAIGN_ID \
  --finding-id FINDING_ID --edits /path/to/edits.json --validate</pre>${s.remediations.length ? s.remediations.map((r) => `<div class="list-item"><div><a class="clickable" data-remediation="${esc(r.id)}">${esc(r.title || r.finding_id)}</a><small>${esc(r.branch || r.id)} · ${esc(date(r.created_at))}</small></div>${badge(r.status)}</div>`).join("") : empty("No proposals yet", "Proposals appear here when the local remediation command completes.")}</section>`;
  } else if (route === "integrations") {
    $("#content").innerHTML =
      `<section class="panel"><h2>Connect your workflow</h2><p class="instructions">The community API uses a local bearer token. The routes below serve metadata for automation and observability. Full assessment evidence is available separately through the campaign API.</p><div class="list-item"><div>n8n / automation<small>Use an HTTP Request node with Bearer authentication.</small></div><code>POST /api/v1/campaigns</code></div><div class="list-item"><div>Grafana / Prometheus<small>Severity counts and queue health; no target labels.</small></div><code>GET /metrics</code></div><div class="list-item"><div>Splunk / SIEM<small>Poll the metadata feed and deduplicate by finding id.</small></div><code>GET /api/v1/integrations/findings</code></div><div class="list-item"><div>Live change notifications<small>Server-sent revision events with bearer authentication.</small></div><code>GET /api/v1/events</code></div><pre>curl -H "Authorization: Bearer $DARKMOON_DASHBOARD_TOKEN" \
  http://127.0.0.1:8780/api/v1/integrations/findings</pre><p class="instructions">These are community endpoints. Existing plugins written for the proprietary Pro API need an adapter; their API compatibility is not assumed.</p></section>`;
  } else if (window.renderWorkspace) {
    window.renderWorkspace(route).catch(fail);
  }
}

async function showCampaign(id) {
  campaignId = id;
  const c = await api(`/api/v1/campaigns/${encodeURIComponent(id)}`);
  $("#detail-title").textContent = c.name || c.id;
  $("#detail-body").innerHTML =
    `${badge(c.status)} <span class="subtle">${esc(c.target?.host || "")} · ${esc(date(c.date))}</span><div class="report-actions">${["md", "pdf", "json"].map((format) => `<button class="secondary" data-export="${format}" data-cid="${esc(id)}">Download ${format.toUpperCase()}</button>`).join("")}<button class="secondary" data-report-preview="${esc(id)}">Preview report</button><button class="secondary" data-protected-pdf="${esc(id)}">Signed / encrypted PDF</button><button class="secondary" id="open-map">Explore surface →</button></div><p class="detail-text">${esc(c.executive_summary || "No executive summary recorded yet.")}</p>${findingsTable(c.findings)}`;
  $("#detail").showModal();
}
async function showFinding(id, cid) {
  const c = await api(`/api/v1/campaigns/${encodeURIComponent(cid)}`),
    f = c.findings.find((x) => x.id === id);
  if (!f) throw new Error("Finding not found");
  $("#detail-title").textContent = f.title || f.id;
  const evidence =
    typeof f.evidence === "object"
      ? JSON.stringify(f.evidence, null, 2)
      : f.evidence;
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
      )}<div class="detail-label">Recorded evidence</div><pre>${esc(evidence || f.evidence_output || "No evidence recorded")}</pre>${f.evidence_commands ? `<pre>${esc(f.evidence_commands)}</pre>` : ""}<div class="detail-label">Remediation guidance</div><div class="detail-text">${esc(f.remediation || "No guidance recorded.")}</div>${["confirmed", "exploited"].includes(f.status) ? `<div class="report-actions"><button class="primary" data-prepare-fix="${esc(id)}" data-cid="${esc(cid)}">Prepare local fix →</button></div>` : ""}<div class="detail-label">Operator triage</div><div class="toolbar"><select id="triage-status">${["unconfirmed", "confirmed", "exploited", "false_positive", "accepted_risk", "remediated", "resolved"].map((x) => `<option value="${x}" ${f.status === x ? "selected" : ""}>${x.replaceAll("_", " ")}</option>`).join("")}</select><button class="secondary" data-triage="${esc(id)}" data-cid="${esc(cid)}">Save triage</button></div><small>Operator triage does not constitute a validated remediation retest.</small>`;
  if (!$("#detail").open) $("#detail").showModal();
}
async function exportReport(cid, format) {
  const res = await fetch(
    `/api/v1/campaigns/${encodeURIComponent(cid)}/report.${format}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) throw new Error((await res.json()).error);
  const url = URL.createObjectURL(await res.blob()),
    a = document.createElement("a");
  a.href = url;
  a.download = `${cid}.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function showJob(id) {
  const j = await api(`/api/v1/jobs/${encodeURIComponent(id)}`);
  currentDetailJob = id;
  $("#detail-title").textContent = j.spec.name;
  $("#detail-body").innerHTML =
    `${badge(j.status)}<p class="detail-text">${esc(j.error || "Launcher output is shown below. Cancelling the launcher may leave work running inside the agent container; inspect its session before rerunning.")}</p><pre id="job-log"></pre>`;
  const res = await fetch(`/api/v1/jobs/${encodeURIComponent(id)}/log`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  $("#job-log").textContent = await res.text();
  if (!$("#detail").open) $("#detail").showModal();
}
function launchDialog(schedule = false) {
  scheduleMode = schedule;
  $("#launch-title").textContent = schedule
    ? "New recurring assessment"
    : "New assessment";
  $("#launch-submit").textContent = schedule
    ? "Create schedule →"
    : "Start assessment →";
  $("#schedule-fields").hidden = !schedule;
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
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});
$("#login").addEventListener("cancel", (e) => e.preventDefault());
$("#detail").addEventListener("close", () => {
  currentDetailJob = "";
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
    const values = Object.fromEntries(new FormData(e.target));
    values.remediate = e.target.elements.remediate.checked;
    if (scheduleMode) {
      values.interval_seconds = Math.round(Number(values.hours) * 3600);
      if (values.first_run)
        values.next_run = new Date(values.first_run).toISOString();
    }
    await api(`/api/v1/${scheduleMode ? "schedules" : "campaigns"}`, {
      method: "POST",
      body: JSON.stringify(values),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
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
  const b = e.target.closest(
    "button,[data-campaign],[data-finding],[data-job],[data-remediation]",
  );
  if (!b) return;
  try {
    if (b.classList.contains("close-dialog")) {
      b.closest("dialog").close();
      currentDetailJob = "";
    } else if (b.dataset.campaign) await showCampaign(b.dataset.campaign);
    else if (b.dataset.finding)
      await showFinding(b.dataset.finding, b.dataset.cid);
    else if (b.dataset.export)
      await exportReport(b.dataset.cid, b.dataset.export);
    else if (b.dataset.patch) {
      const res = await fetch(
        `/api/v1/remediations/${encodeURIComponent(b.dataset.patch)}/patch`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error((await res.json()).error);
      const url = URL.createObjectURL(await res.blob()),
        a = document.createElement("a");
      a.href = url;
      a.download = b.dataset.patch + ".patch";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else if (b.dataset.job) await showJob(b.dataset.job);
    else if (b.dataset.cancel) {
      await api(`/api/v1/jobs/${b.dataset.cancel}/cancel`, {
        method: "POST",
        body: "{}",
      });
      await refresh();
    } else if (b.id === "new-schedule") launchDialog(true);
    else if (b.id === "open-map") {
      $("#detail").close();
      location.hash = "surface";
    } else if (b.dataset.toggleSchedule) {
      const s = snapshot.schedules.find(
        (x) => x.id === b.dataset.toggleSchedule,
      );
      await api(`/api/v1/schedules/${s.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !s.enabled }),
      });
      await refresh();
    } else if (b.dataset.deleteSchedule) {
      await api(`/api/v1/schedules/${b.dataset.deleteSchedule}`, {
        method: "DELETE",
      });
      await refresh();
    } else if (b.dataset.prepareFix) {
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
      const r = snapshot.remediations.find(
        (x) => x.id === b.dataset.remediation,
      );
      $("#detail-title").textContent = r.title || r.id;
      $("#detail-body").innerHTML =
        `${badge(r.status)} ${r.patch_path ? `<button class="secondary" data-patch="${esc(r.id)}">Download patch</button>` : ""}<pre>${esc(JSON.stringify(r, null, 2))}</pre>`;
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
  if (e.target.id === "severity-filter") {
    selectedSeverity = e.target.value;
    render();
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "finding-search") {
    const pos = e.target.selectionStart;
    selectedSearch = e.target.value;
    render();
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
  if (currentDetailJob && $("#detail").open)
    showJob(currentDetailJob).catch(fail);
}, 2000);

async function drawSurface(cid, signal) {
  const graph = await api(`/api/v1/campaigns/${encodeURIComponent(cid)}/graph`);
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
    frame;
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
      ctx.strokeStyle = e.kind === "observed" ? "#9f93df" : "#3a5067";
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
      selected = n.id;
      const linked = n.linked;
      info.innerHTML = `<h3>${esc(n.label || n.id)}</h3><pre>${esc(JSON.stringify(Object.fromEntries(Object.entries(n).filter(([k]) => !["p", "screen", "depth", "linked", "risk"].includes(k))), null, 2))}</pre><h3>${linked.length} explicitly linked findings</h3>${linked.map((f) => `<div class="list-item clickable" data-finding="${esc(f.id)}" data-cid="${esc(cid)}">${badge(f.severity)} ${esc(f.title)}</div>`).join("")}`;
    },
    { signal },
  );
  const tour = $("#surface-tour"),
    locations = nodes.filter((n) => n.linked.length);
  let tourTimer = null,
    tourIndex = 0;
  tour.disabled = !locations.length;
  tour.addEventListener(
    "click",
    () => {
      if (tourTimer) {
        clearInterval(tourTimer);
        tourTimer = null;
        tour.textContent = "Tour finding locations";
        return;
      }
      tour.textContent = "Stop tour";
      const advance = () => {
        const n = locations[tourIndex++ % locations.length];
        selected = n.id;
        angle = -Math.atan2(n.p[2], n.p[0]) + 0.25;
        info.innerHTML = `<h3>${esc(n.label || n.id)}</h3><p class="instructions">Finding-location tour. Positions are grouped by node type; the tour does not assert an exploitation chain.</p>${n.linked.map((f) => `<div class="list-item clickable" data-finding="${esc(f.id)}" data-cid="${esc(cid)}"><div>${badge(f.severity)} ${esc(f.title)}<small>${esc([f.mitre_attack_id, f.mitre_attack_name].filter(Boolean).join(" · "))}</small></div></div>`).join("")}`;
      };
      advance();
      tourTimer = setInterval(advance, 2500);
    },
    { signal },
  );
  signal.addEventListener(
    "abort",
    () => {
      cancelAnimationFrame(frame);
      if (tourTimer) clearInterval(tourTimer);
    },
    { once: true },
  );
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
