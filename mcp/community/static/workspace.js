"use strict";
// Additional workspace pages share the authenticated API and literal-data
// rendering helpers from app.js. No third-party scripts or remote assets.
(() => {
  let formState = null;
  const fields = (specs) =>
    specs
      .map(
        ([name, label, type = "text", options = []]) =>
          `<label>${esc(label)}${type === "select" ? `<select name="${name}">${options.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("")}</select>` : type === "textarea" ? `<textarea name="${name}" rows="3"></textarea>` : `<input name="${name}" type="${type}" ${type === "checkbox" || label.includes("optional") || name === "base_url" ? "" : "required"} autocomplete="off">`}</label>`,
      )
      .join("");
  function openForm(kind, title, specs, context = {}) {
    formState = { kind, ...context };
    $("#workspace-title").textContent = title;
    $("#workspace-fields").innerHTML = fields(specs);
    $("#workspace-error").textContent = "";
    if ($("#detail").open) $("#detail").close();
    $("#workspace-dialog").showModal();
  }
  function details(title, html) {
    $("#detail-title").textContent = title;
    $("#detail-body").innerHTML = html;
    if (!$("#detail").open) $("#detail").showModal();
  }
  function chart(canvas, series) {
    const ctx = canvas.getContext("2d"),
      rect = canvas.getBoundingClientRect(),
      ratio = devicePixelRatio || 1;
    canvas.width = rect.width * ratio;
    canvas.height = 240 * ratio;
    ctx.scale(ratio, ratio);
    const colors = ["#a6efc1", "#a99af6", "#f5b27b", "#ff8c9a", "#a6c8e7"];
    const ticks = [
      ...new Set(series.flatMap((s) => s.points.map((p) => p.t))),
    ].sort();
    const max = Math.max(
      1,
      ...series.flatMap((s) => s.points.map((p) => p.value)),
    );
    ctx.strokeStyle = "#354054";
    ctx.beginPath();
    ctx.moveTo(32, 15);
    ctx.lineTo(32, 200);
    ctx.lineTo(rect.width - 15, 200);
    ctx.stroke();
    ctx.font = "10px system-ui";
    ctx.fillStyle = "#8995a9";
    ctx.fillText(String(max), 5, 20);
    ctx.fillText("0", 15, 200);
    ticks.forEach((t, i) => {
      if (i === 0 || i === ticks.length - 1)
        ctx.fillText(
          t.slice(0, 10),
          32 + (i * (rect.width - 100)) / Math.max(1, ticks.length - 1),
          220,
        );
    });
    series.forEach((s, i) => {
      ctx.strokeStyle = colors[i % colors.length];
      ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath();
      s.points.forEach((p, j) => {
        const x =
            40 +
            (ticks.indexOf(p.t) * (rect.width - 100)) /
              Math.max(1, ticks.length - 1),
          y = 195 - (p.value / max) * 170;
        j ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
      for (const p of s.points) {
        const x =
            40 +
            (ticks.indexOf(p.t) * (rect.width - 100)) /
              Math.max(1, ticks.length - 1),
          y = 195 - (p.value / max) * 170;
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillText(s.key, 45 + i * 90, 238);
    });
  }
  window.renderWorkspace = async function (page) {
    if (page === "projects") {
      const result = await api("/api/v1/projects");
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Projects and assessment history</h3><p>Compare evidence and severity counts across campaigns for the same target.</p></div><button class="primary" data-workspace="project">+ Add project</button></div>${result.data.map((p) => `<div class="list-item"><div><a class="clickable" data-project-analytics="${esc(p.id)}">${esc(p.name || p.id)}</a><small>${esc(p.description || "")}</small></div><button class="secondary" data-project-analytics="${esc(p.id)}">Analytics →</button></div>`).join("") || empty("No projects yet")}</section>`;
    } else if (page === "credentials") {
      const result = await api("/api/v1/credentials");
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Encrypted credentials</h3><p>Use opaque references in runs and provider profiles. Saved secrets are never returned.</p></div><button class="primary" data-workspace="credential">+ Add credential</button></div>${result.data.map((c) => `<div class="list-item"><div>${esc(c.name)}<small>${esc(c.provider)} · ${esc(c.id)} · ${esc(c.hint)}</small></div><button class="secondary" data-delete-credential="${esc(c.id)}">Delete</button></div>`).join("") || empty("No saved credentials")}</section>`;
    } else if (page === "webhooks") {
      const result = await api("/api/v1/webhooks");
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Signed webhook subscriptions</h3><p>HMAC signatures, event ids, timestamps and bounded retries. Delivery contains safe metadata only.</p></div><button class="primary" data-workspace="webhook">+ Add webhook</button></div>${result.data.map((h) => `<div class="list-item"><div>${esc(h.url)}<small>${esc(h.events.join(", ") || "All events")}</small></div><div><button class="secondary" data-webhook-deliveries="${esc(h.id)}">Deliveries</button> <button class="secondary" data-delete-webhook="${esc(h.id)}">Delete</button></div></div>`).join("") || empty("No subscriptions", "Registering a subscription enables delivery when matching events occur.")}</section>`;
    } else if (page === "retests") {
      const result = await api("/api/v1/retest");
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Reassessment and remediation verdicts</h3><p>Absence is reported as not observed. Fixed requires recorded before/after remediation proof.</p></div><button class="primary" data-workspace="retest">+ Retest assessment</button></div>${result.data.map((r) => `<div class="list-item"><div><a class="clickable" data-retest-detail="${esc(r.id)}">${esc(r.base_campaign_id)}</a><small>${esc(date(r.created_at))}</small></div>${badge(r.status)}</div>`).join("") || empty("No retests yet")}</section>`;
    } else if (page === "settings") {
      const [who, users, providers] = await Promise.all([
        api("/api/v1/auth/me"),
        api("/api/v1/auth/users"),
        api("/api/v1/system/providers"),
      ]);
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Accounts and access</h3><p>Signed in as ${esc(who.user.username)} · ${esc(who.user.role)}</p></div><button class="primary" data-workspace="account">+ Add account</button></div>${users.data.map((u) => `<div class="list-item"><div>${esc(u.username)}<small>${esc(u.id)}</small></div>${badge(u.role)}</div>`).join("") || empty("No password accounts", "Create an account here or configure your OIDC provider. The workspace token remains an administrator recovery method.")}<p class="instructions">OIDC uses the configured issuer, client id, redirect URI, PKCE and nonce verification. Local passwords and SSO identities issue short-lived, revocable sessions.</p><button class="secondary" data-workspace="password">Change my password</button></section><section class="panel"><div class="section-top"><div><h3>LLM provider profiles</h3><p>Keys stay encrypted until you explicitly apply a profile to the existing agent environment.</p></div><button class="primary" data-workspace="provider">+ Add provider</button></div>${providers.data.map((p) => `<div class="list-item"><div>${esc(p.provider)} / ${esc(p.model)}<small>${esc(p.mode)} · ${esc(p.base_url)}</small></div><button class="secondary" data-apply-provider="${esc(p.id)}">Apply profile</button></div>`).join("") || empty("No saved provider profiles")}<small>Applying a profile updates .opencode.env. Recreate the existing OpenCode service to load it.</small></section><section class="panel"><div class="section-top"><div><h3>Installation health</h3><p>Inspect dependencies, paths and the operator-controlled integrity guard.</p></div><div><button class="secondary" data-doctor="1">Run diagnostics</button> <button class="secondary" data-updates="1">Check image updates</button></div></div><p class="instructions">Enforcement is opt-in. After reviewing your source and Compose policy, create the integrity baseline with the documented local command. Licensing and vendor activation are not part of this independent implementation.</p></section>`;
    }
  };
  function markdownPreview(markdown) {
    const root = document.createElement("div");
    root.className = "report-preview";
    let code = null,
      table = null;
    for (const line of markdown.split("\n")) {
      if (line.startsWith("```")) {
        if (code) {
          code = null;
        } else {
          code = document.createElement("pre");
          root.append(code);
        }
        table = null;
        continue;
      }
      if (code) {
        code.textContent += line + "\n";
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)/);
      if (heading) {
        const h = document.createElement("h" + heading[1].length);
        h.textContent = heading[2];
        root.append(h);
        table = null;
        continue;
      }
      if (line.startsWith("|")) {
        if (/^\|[\s:|\-]+\|$/.test(line)) continue;
        if (!table) {
          table = document.createElement("table");
          root.append(table);
        }
        const tr = document.createElement("tr");
        for (const cell of line.slice(1, -1).split("|")) {
          const td = document.createElement("td");
          td.textContent = cell.trim().replaceAll("**", "").replaceAll("`", "");
          tr.append(td);
        }
        table.append(tr);
        continue;
      }
      table = null;
      if (line.trim()) {
        const p = document.createElement("p");
        p.textContent = line;
        root.append(p);
      }
    }
    return root;
  }
  document.addEventListener("click", async (event) => {
    const button = event.target.closest(
      "button,[data-project-analytics],[data-retest-detail]",
    );
    if (!button) return;
    try {
      const action = button.dataset.workspace;
      if (action === "account")
        openForm("account", "Create account", [
          ["username", "Username"],
          ["password", "Password (at least 12 characters)", "password"],
          ["role", "Role", "select", ["viewer", "analyst", "admin"]],
        ]);
      if (action === "password")
        openForm("password", "Change password", [
          ["old_password", "Current password", "password"],
          ["new_password", "New password (at least 12 characters)", "password"],
        ]);
      if (action === "credential")
        openForm("credential", "Store encrypted credential", [
          ["name", "Name"],
          ["provider", "Provider (github, local-model, aws, …)"],
          ["username", "Username (optional)"],
          ["secret", "Secret", "password"],
        ]);
      if (action === "webhook")
        openForm("webhook", "Register webhook", [
          ["url", "HTTPS receiver URL"],
          ["events", "Events (comma-separated, or *)"],
          ["secret", "Signing secret (at least 24 characters)", "password"],
        ]);
      if (action === "provider")
        openForm("provider", "Save provider profile", [
          ["provider", "Provider id"],
          ["mode", "Mode", "select", ["local", "cloud", "anthropic"]],
          ["model", "Model id"],
          ["base_url", "Base URL (local / Anthropic)"],
          ["credential_id", "Saved credential id (optional for local)"],
        ]);
      if (action === "project")
        openForm("project", "Create project", [
          ["name", "Project name"],
          ["description", "Description", "textarea"],
        ]);
      if (action === "retest")
        openForm("retest", "Retest an assessment", [
          ["campaign_id", "Base campaign id"],
          ["finding_ids", "Finding ids (optional, comma-separated)"],
        ]);
      if (button.dataset.protectedPdf)
        openForm(
          "protected_pdf",
          "Signed and encrypted PDF",
          [
            [
              "password",
              "Report password (at least 12 characters)",
              "password",
            ],
          ],
          { campaignId: button.dataset.protectedPdf },
        );
      if (button.dataset.reportPreview) {
        const r = await api(
          `/api/v1/campaigns/${button.dataset.reportPreview}/report`,
        );
        details("Assessment report", "");
        $("#detail-body").append(markdownPreview(r.content));
      }
      if (button.dataset.projectAnalytics) {
        const result = await api(
          `/api/v1/projects/${button.dataset.projectAnalytics}/analytics`,
        );
        details(
          "Project vulnerability evolution",
          `<div class="cards"><div class="card">Campaigns<div class="number">${result.data.campaigns_count}</div></div><div class="card">Findings<div class="number">${result.data.total_vulnerabilities}</div></div></div><canvas class="analytics-chart" id="project-chart"></canvas><p class="instructions">Counts reflect recorded findings per campaign. Compare scope before interpreting changes as improvements.</p>${campaignsTable(result.campaigns)}`,
        );
        chart($("#project-chart"), result.timeseries.series);
      }
      if (button.dataset.deleteCredential) {
        await api(`/api/v1/credentials/${button.dataset.deleteCredential}`, {
          method: "DELETE",
        });
        await window.renderWorkspace("credentials");
      }
      if (button.dataset.deleteWebhook) {
        await api(`/api/v1/webhooks/${button.dataset.deleteWebhook}`, {
          method: "DELETE",
        });
        await window.renderWorkspace("webhooks");
      }
      if (button.dataset.webhookDeliveries) {
        const r = await api(
          `/api/v1/webhooks/${button.dataset.webhookDeliveries}/deliveries`,
        );
        details(
          "Delivery history",
          `<pre>${esc(JSON.stringify(r.data, null, 2))}</pre>`,
        );
      }
      if (button.dataset.retestDetail) {
        const r = await api(`/api/v1/retest/${button.dataset.retestDetail}`);
        details(
          "Retest verdicts",
          `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`,
        );
      }
      if (button.dataset.applyProvider) {
        const r = await api(
          `/api/v1/system/providers/${button.dataset.applyProvider}/apply`,
          { method: "POST", body: "{}" },
        );
        details("Provider applied", `<p>${esc(r.note)}</p>`);
      }
      if (button.dataset.updates) {
        const result = await api("/api/v1/system/update-status?check=1");
        details(
          "Image update status",
          `<pre>${esc(JSON.stringify(result, null, 2))}</pre>`,
        );
      }
      if (button.dataset.doctor) {
        const r = await api("/api/v1/system/doctor");
        details(
          "Installation diagnostics",
          `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`,
        );
      }
    } catch (error) {
      fail(error);
    }
  });
  $("#workspace-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const raw = Object.fromEntries(new FormData(event.target)),
        kind = formState.kind;
      let result;
      if (kind === "account")
        result = await api("/api/v1/auth/users", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      if (kind === "password") {
        result = await api("/api/v1/auth/password", {
          method: "POST",
          body: JSON.stringify(raw),
        });
        $("#workspace-dialog").close();
        lock();
        return;
      }
      if (kind === "credential")
        result = await api("/api/v1/credentials", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      if (kind === "provider")
        result = await api("/api/v1/system/providers", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      if (kind === "project")
        result = await api("/api/v1/projects", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      if (kind === "webhook") {
        raw.events = raw.events
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean);
        result = await api("/api/v1/webhooks", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      }
      if (kind === "retest") {
        raw.finding_ids = raw.finding_ids
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean);
        result = await api("/api/v1/retest", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      }
      if (kind === "protected_pdf") {
        const res = await fetch(
          `/api/v1/campaigns/${encodeURIComponent(formState.campaignId)}/report/pdf`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ password: raw.password, sign: true }),
          },
        );
        if (!res.ok) throw new Error((await res.json()).error);
        const url = URL.createObjectURL(await res.blob()),
          a = document.createElement("a");
        a.href = url;
        a.download = `${formState.campaignId}-protected.pdf`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      $("#workspace-dialog").close();
      await refresh();
    } catch (error) {
      $("#workspace-error").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  $("#workspace-dialog").addEventListener("close", () => {
    $("#workspace-fields").replaceChildren();
  });
  $("#sso-login").addEventListener("click", async () => {
    try {
      const result = await api("/api/v1/auth/oidc/start");
      sessionStorage.setItem("darkmoon-oidc-state", result.state);
      location.assign(result.url);
    } catch (error) {
      $("#login-error").textContent = error.message;
    }
  });
  fetch("/api/v1/auth/config")
    .then((r) => r.json())
    .then((c) => {
      $("#sso-login").hidden = !c.oidc?.enabled;
    })
    .catch(() => {});
  const callback = new URLSearchParams(location.search);
  if (location.pathname === "/callback") {
    const state = sessionStorage.getItem("darkmoon-oidc-state");
    sessionStorage.removeItem("darkmoon-oidc-state");
    if (state && state === callback.get("state")) {
      fetch("/api/v1/auth/oidc/callback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: callback.get("code"), state }),
      })
        .then(async (r) => {
          const result = await r.json();
          if (!r.ok) throw new Error(result.error);
          token = result.token;
          history.replaceState(null, "", "/");
          await refresh();
          $("#login").close();
          connect();
        })
        .catch((error) => {
          $("#login-error").textContent = error.message;
        });
    } else {
      $("#login-error").textContent =
        "SSO browser state did not match. Start sign-in again.";
    }
  }
})();
