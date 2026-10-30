"use strict";
// Additional workspace pages share the authenticated API and literal-data
// rendering helpers from app.js. No third-party scripts or remote assets.
(() => {
  let formState = null;
  let choices = null;
  const optionsHtml = (items) =>
    items
      .map((x) => {
        const value = typeof x === "string" ? x : x.value;
        const label = typeof x === "string" ? x : x.label;
        return `<option value="${esc(value)}">${esc(label)}</option>`;
      })
      .join("");
  const credentials = (capability) => [
    { value: "", label: "None / use existing provider login" },
    ...(choices.credential_choices?.[capability] || []).map((c) => ({
      value: c.id,
      label: `${c.name} (${c.provider})`,
    })),
  ];
  async function loadChoices(signal) {
    choices = await api("/api/v1/options", {signal});
    return choices;
  }
  function providerModels() {
    const form = $("#workspace-form"),
      pid = form.elements.provider.value;
    const provider = choices.opencode?.providers.find((p) => p.id === pid);
    const model = form.elements.model;
    if (model) {
      model.innerHTML = optionsHtml([
        ...(provider?.models || []).map((m) => ({
          value: m.id,
          label: m.name,
        })),
        { value: "__custom__", label: "Custom model…" },
      ]);
      const active = choices.opencode?.active_model || "";
      if (
        active.startsWith(pid + "/") &&
        [...model.options].some((o) => o.value === active.slice(pid.length + 1))
      )
        model.value = active.slice(pid.length + 1);
      if (form.elements.base_url)
        form.elements.base_url.value =
          provider?.base_url ||
          (pid === "ollama" ? "http://host.docker.internal:11434/v1" : "");
      form.elements.mode.value = provider?.base_url
        ? pid === "anthropic"
          ? "anthropic"
          : "local"
        : pid === "ollama" || pid === "local"
          ? "local"
          : "cloud";
    }
    if (form.elements.auth_method)
      form.elements.auth_method.innerHTML = optionsHtml([
        { value: "api", label: "Saved credential / API key" },
        ...(provider?.methods || [])
          .filter((m) => m.type === "oauth")
          .map((m) => ({ value: String(m.index), label: m.label })),
      ]);
    customFields();
  }
  function customFields() {
    const f = $("#workspace-form");
    for (const [select, input] of [
      ["provider", "custom_provider"],
      ["model", "custom_model"],
    ]) {
      if (f.elements[input]) {
        const custom = f.elements[select].value === "__custom__";
        f.elements[input].closest("label").hidden = !custom;
        f.elements[input].required = custom;
      }
    }
    if (f.elements.auth_method) {
      const apiKey = f.elements.auth_method.value === "api";
      for (const key of ["credential_id", "secret"])
        f.elements[key].closest("label").hidden = !apiKey;
    }
  }
  function retestFindings() {
    const f = $("#workspace-form");
    if (!f.elements.finding_ids) return;
    f.elements.finding_ids.innerHTML = optionsHtml([
      { value: "", label: "All findings in this assessment" },
      ...choices.findings
        .filter((v) => v.campaign_id === f.elements.campaign_id.value)
        .map((v) => ({ value: v.id, label: `${v.title} (${v.severity})` })),
    ]);
  }
  window.populateLaunch = async (signal) => {
    await loadChoices(signal);
    if (signal?.aborted) return;
    const f = $("#launch-form");
    f.reset();
    f.elements.known_target.innerHTML = optionsHtml([
      { value: "", label: "New target…" },
      ...choices.targets.map((t) => ({
        value: t.id,
        label: t.name || t.host || t.ip,
      })),
    ]);
    for (const key of [
      "assessment_credential_id",
      "assessment_token_id",
      "credential_id",
    ])
      f.elements[key].innerHTML = optionsHtml(
        credentials({
          credential_id: "source_checkout",
          assessment_token_id: "assessment_token",
          assessment_credential_id: "assessment_login",
        }[key]).map((c, i) =>
          i
            ? c
            : {
                value: "",
                label:
                  key === "credential_id"
                    ? "No SCM credential"
                    : key === "assessment_token_id"
                      ? "No saved target token"
                      : "No saved target login",
              },
        ),
      );
    for (const key of ["known_targets", "known_out_of_scope"])
      f.elements[key].innerHTML = optionsHtml(
        choices.targets.map((t) => ({
          value: t.host || t.ip,
          label: t.name || t.host || t.ip,
        })),
      );
    for (const key of ["focus", "exclude"])
      f.elements[key].innerHTML = optionsHtml(choices.assessment[key]);
    f.elements.severity.innerHTML = optionsHtml([
      { value: "", label: "Runtime default" },
      ...choices.assessment.severity_caps,
    ]);
    f.elements.noise.innerHTML = optionsHtml(choices.assessment.noise);
    f.elements.noise.value = "moderate";
    f.elements.format.innerHTML = optionsHtml(choices.assessment.formats);
    f.elements.preset.innerHTML = optionsHtml(
      choices.assessment.presets.map((p) => ({ value: p.id, label: p.label })),
    );
    $("#source-repositories").innerHTML = optionsHtml(choices.repositories);
    if (choices.targets.length) {
      f.elements.known_target.value = choices.targets[0].id;
      fillTarget();
    }
    f.elements.first_run.value = new Date(
      Date.now() + 3600000 - new Date().getTimezoneOffset() * 60000,
    )
      .toISOString()
      .slice(0, 16);
    updateLaunchPreview();
  };
  window.launchValues = (form) => {
    const data = new FormData(form),
      values = Object.fromEntries(data);
    for (const key of ["focus", "exclude"])
      values[key] = [
        ...new Set(
          [
            ...data.getAll(key),
            ...(values[key + "_extra"] || "").split(",").map((x) => x.trim()),
          ].filter(Boolean),
        ),
      ].join(",");
    for (const [key, known] of [
      ["targets", "known_targets"],
      ["out_of_scope", "known_out_of_scope"],
    ])
      values[key] = [
        ...new Set(
          [
            ...data.getAll(known),
            ...(values[key] || "").split(",").map((x) => x.trim()),
          ].filter(Boolean),
        ),
      ];
    for (const key of [
      "focus_extra",
      "exclude_extra",
      "known_targets",
      "known_out_of_scope",
      "known_target",
      "preset",
    ])
      delete values[key];
    values.remediate = form.elements.remediate.checked;
    return values;
  };
  function updateLaunchPreview() {
    const f = $("#launch-form"),
      v = window.launchValues(f);
    const parts = [
      "TARGET: " + (v.target || "<choose a target>"),
      "PROGRAM=" + JSON.stringify(v.name || "Assessment"),
    ];
    for (const key of ["focus", "exclude", "noise", "severity", "format"])
      if (v[key]) parts.push(key.toUpperCase() + "=" + v[key]);
    if (v.targets.length) parts.push("TARGETS=" + v.targets.join(","));
    if (v.out_of_scope.length) parts.push("OUT=" + v.out_of_scope.join(","));
    if (v.rules) parts.push("RULES=" + JSON.stringify(v.rules));
    if (v.safe_harbor_applies)
      parts.push("SAFE_HARBOR=" + v.safe_harbor_applies);
    $("#launch-preview").textContent = parts.join(" ");
  }
  document.addEventListener("input", (e) => {
    if (e.target.closest("#launch-form")) updateLaunchPreview();
  });
  document.addEventListener("change", (e) => {
    if (!e.target.closest("#launch-form")) return;
    if (e.target.name === "preset") {
      const f = $("#launch-form"),
        preset = choices.assessment.presets.find(
          (p) => p.id === f.elements.preset.value,
        );
      for (const key of ["focus", "exclude"])
        for (const o of f.elements[key].options)
          o.selected = preset[key].includes(o.value);
      for (const key of ["noise", "format"])
        f.elements[key].value = preset[key];
      f.elements.focus_extra.value = "";
      f.elements.exclude_extra.value = "";
    }
    updateLaunchPreview();
  });
  window.renderIntegrations = async () => {
    await loadChoices();
    if (route !== "integrations") return;
    $("#content").innerHTML =
      `<section class="panel"><h2>Connect your workflow</h2><p>Create a dedicated account in Settings for external clients. Use this installation’s URL, <code>${esc(location.origin)}</code>, rather than the upstream Pro port 8000. For Docker-hosted clients, use a hostname reachable from that container; localhost there refers to the client container. n8n supports username/password login at <code>POST /api/v1/auth/login</code>; the workspace bearer token is an administrator recovery credential.</p><p>Campaigns, findings, reports, retests and metrics are available. Proposal APIs are read-only. Publishing remains a separate operator action.</p><p><a href="#webhooks">Signed webhook delivery and event subscriptions →</a></p><p>n8n: install <code>n8n-nodes-darkmoon</code>, configure a Darkmoon API credential, test the connection, then choose Run Pentest or a read-only operation. Wait for completion polls the run; local proposals do not imply a published PR. A launch severity cap differs from a CI/n8n minimum reporting threshold.</p>${choices.assessment.integrations.map((i) => `<div class="list-item"><div><a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.name)}</a><small>${esc(i.usage)}</small></div></div>`).join("")}<p>Imported packages are available under <code>integrations/upstream</code>; installation compatibility still depends on the host product.</p><p><a href="${esc(choices.assessment.sources.benchmark)}" target="_blank" rel="noopener noreferrer">Benchmark methodology and recorded lab runs</a> · <a href="${esc(choices.assessment.sources.scope)}" target="_blank" rel="noopener noreferrer">Upstream scope reference</a></p></section>`;
  };
  let sourceRequest = 0, sourceExpiry;
  function clearSourceFiles() {
    sourceRequest++;
    clearTimeout(sourceExpiry);
    const f = $("#remediation-form");
    if (f) { f.elements.source_files.innerHTML = ""; f.elements.files.value = ""; }
  }
  window.addEventListener("blur", clearSourceFiles);
  document.addEventListener("visibilitychange", () => { if (document.hidden) clearSourceFiles(); });
  document.addEventListener("close", event => { if (event.target.contains?.($("#remediation-form"))) clearSourceFiles(); }, true);
  async function loadSourceFiles() {
    clearSourceFiles();
    const request = sourceRequest, f = $("#remediation-form"), repo = f.elements.repo.value;
    if (!repo) return;
    const session = token, deadline = Date.now() + 45000;
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(repo));
    const id = "repo_" + [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, "0")).join("");
    const grant = await api("/api/v1/evidence/grants", {method:"POST", body:JSON.stringify({kind:"source",id})});
    const result = await api("/api/v1/source-files", {method:"POST",
      headers:{"X-Darkmoon-Evidence-Grant":grant.grant}, body:JSON.stringify({repository_id:id})});
    if (request !== sourceRequest || token !== session || f.elements.repo.value !== repo || Date.now() >= deadline || !f.closest("dialog").open) return;
    f.elements.source_files.innerHTML = optionsHtml(result.files);
    $("#remediation-error").textContent = result.truncated ? "Only part of the tracked source list is available." : "";
    sourceExpiry = setTimeout(clearSourceFiles, deadline - Date.now());
  }
  window.populateRemediation = async () => {
    await loadChoices();
    $("#source-repositories").innerHTML = optionsHtml(choices.repositories);
    const f = $("#remediation-form");
    f.reset();
    const localRepos = choices.repositories.filter(
      (p) => !p.includes("://") && !p.startsWith("git@"),
    );
    if (localRepos.length) {
      f.elements.repo.value = localRepos[0];
      clearSourceFiles();
    }
  };
  function fillTarget() {
    const f = $("#launch-form"),
      target = choices.targets.find(
        (t) => t.id === f.elements.known_target.value,
      );
    f.elements.target.value = target?.host || target?.ip || "";
    f.elements.name.value = target
      ? `Review: ${target.name || target.host || target.ip}`
      : "";
    updateLaunchPreview();
  }
  document.addEventListener("change", (event) => {
    const f = event.target.closest("form");
    if (f?.id === "remediation-form" && event.target.name === "source_files")
      f.elements.files.value = [...event.target.selectedOptions]
        .map((o) => o.value)
        .join("\n");
    if (f?.id === "remediation-form" && event.target.name === "repo")
      clearSourceFiles();
    if (f?.id === "launch-form" && event.target.name === "known_target")
      fillTarget();
    if (f?.id !== "workspace-form") return;
    if (event.target.name === "provider") providerModels();
    if (event.target.name === "model" || event.target.name === "auth_method")
      customFields();
    if (event.target.name === "campaign_id") retestFindings();
  });

  const fields = (specs) =>
    specs
      .map(
        ([name, label, type = "text", options = []]) =>
          `<label>${esc(label)}${["select", "multiple"].includes(type) ? `<select name="${name}" ${type === "multiple" ? "multiple" : ""}>${optionsHtml(options)}</select>` : type === "textarea" ? `<textarea name="${name}" rows="3"></textarea>` : `<input name="${name}" type="${type}" ${type === "checkbox" || label.includes("optional") || name === "base_url" ? "" : "required"} autocomplete="off">`}</label>`,
      )
      .join("");
  function openForm(kind, title, specs, context = {}) {
    formState = { kind, ...context };
    $("#workspace-title").textContent = title;
    $("#workspace-fields").innerHTML = fields(specs);
    $("#workspace-error").textContent = "";
    $("#workspace-form button[type=submit]").textContent =
      kind === "provider_delete" ? "Delete profile" : "Save";
    $("#workspace-form button[type=submit]").disabled = false;
    if ($("#detail").open) $("#detail").close();
    $("#workspace-dialog").showModal();
  }
  function details(title, html) {
    clearDetail();
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
        `<section class="panel"><div class="section-top"><div><h3>Encrypted credentials</h3><p>Use opaque references in runs and provider profiles. Saved secrets are never returned.</p></div><button class="primary" data-workspace="credential">+ Add credential</button></div>${result.data.map((c) => `<div class="list-item"><div>${esc(c.name)}<small>${esc(c.provider)} · ${esc(c.id)} · ${esc(c.hint)}</small></div><button class="secondary" data-detail-credential="${esc(c.id)}">Details</button><button class="secondary" data-delete-credential="${esc(c.id)}">Delete</button></div>`).join("") || empty("No saved credentials")}</section>`;
    } else if (page === "webhooks") {
      const result = await api("/api/v1/webhooks");
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Signed webhook subscriptions</h3><p>HMAC signatures, event ids, timestamps and bounded retries. Delivery contains safe metadata only.</p></div><button class="primary" data-workspace="webhook">+ Add webhook</button></div>${result.data.map((h) => `<div class="list-item"><div>${esc(h.url)}<small>${esc(h.events.join(", ") || "All events")}</small></div><div><button class="secondary" data-webhook-deliveries="${esc(h.id)}">Deliveries</button> <button class="secondary" data-delete-webhook="${esc(h.id)}">Delete</button></div></div>`).join("") || empty("No subscriptions", "Registering a subscription enables delivery when matching events occur.")}</section>`;
    } else if (page === "retests") {
      const result = await api("/api/v1/retest");
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Reassessment and remediation verdicts</h3><p>Absence remains not observed. Local proposal validation does not prove deployment to the assessed target.</p></div><button class="primary" data-workspace="retest">+ Retest assessment</button></div>${result.data.map((r) => `<div class="list-item"><div><a class="clickable" data-retest-detail="${esc(r.id)}">${esc(r.base_campaign_id)}</a><small>${esc(date(r.created_at))}</small></div>${badge(r.status)}</div>`).join("") || empty("No retests yet")}</section>`;
    } else if (page === "settings") {
      const who = await api("/api/v1/auth/me");
      if (who.user.role !== "admin") {
        if (route !== page) return;
        $("#content").innerHTML =
          `<section class="panel"><h3>My account</h3><p>${esc(who.user.username)} · ${esc(who.user.role)}</p>${who.user.authentication === "password" ? `<button class="secondary" data-workspace="password">Change my password</button>` : `<p>Manage this sign-in through ${who.user.authentication === "oidc" ? "your SSO provider" : "the workspace recovery token"}.</p>`}<p>Provider logins and installation settings are managed by your administrator.</p></section>`;
        return;
      }
      const [users, providers] = await Promise.all([
        api("/api/v1/auth/users"),
        api("/api/v1/system/providers"),
        loadChoices(),
      ]);
      if (route !== page) return;
      $("#content").innerHTML =
        `<section class="panel"><div class="section-top"><div><h3>Accounts and access</h3><p>Signed in as ${esc(who.user.username)} · ${esc(who.user.role)}</p></div><button class="primary" data-workspace="account">+ Add account</button></div>${users.data.map((u) => `<div class="list-item"><div>${esc(u.username)}<small>${esc(u.id)}</small></div>${badge(u.role)}</div>`).join("") || empty("No password accounts", "Create an account here or configure your OIDC provider. The workspace token remains an administrator recovery method.")}<p class="instructions">OIDC uses the configured issuer, client id, redirect URI, PKCE and nonce verification. Local passwords and SSO identities issue short-lived, revocable sessions.</p>${who.user.authentication === "password" ? `<button class="secondary" data-workspace="password">Change my password</button>` : `<p>Manage this sign-in through ${who.user.authentication === "oidc" ? "your SSO provider" : "the workspace recovery token"}.</p>`}</section><section class="panel"><div class="section-top"><div><h3>OpenCode providers and logins</h3><p>Active model: ${esc(choices.opencode.active_model || "Not configured")} · ${choices.opencode.live ? "Native server connected" : "Shared files; restart required after changes"}</p>${choices.opencode.warning ? `<p role="alert">${esc(choices.opencode.warning)}</p>` : ""}<button class="secondary" data-workspace="opencode_connect">Connect provider</button> <button class="secondary" data-sync-opencode="1">Sync from OpenCode</button> <button class="secondary" data-bridge-health="1">Check bridge</button></div><button class="primary" data-workspace="provider">+ Add provider</button></div>${choices.opencode.providers
          .filter((p) => p.connected)
          .map(
            (p) =>
              `<p>${esc(p.name)} · connected (${esc(p.auth_type)}) · ${p.models.length} catalog models <button class="secondary" data-disconnect-opencode="${esc(p.id)}">Disconnect</button></p>`,
          )
          .join(
            "",
          )}${providers.data.map((p) => `<div class="list-item provider-profile"><div><strong>${esc(p.name || p.provider)}</strong><small>${esc(p.provider)} / ${esc(p.model)} · ${esc(p.mode)} · ${esc(p.base_url)}</small>${p.last_check ? `<small>Last check: ${esc(p.last_check.status)} · ${esc(date(p.last_check.checked_at))}</small>` : ""}</div><div class="profile-actions"><button class="secondary" data-check-provider="${esc(p.id)}">Check</button><button class="secondary" data-edit-provider="${esc(p.id)}">Edit</button><button class="secondary" data-copy-provider="${esc(p.id)}">Duplicate</button><button class="secondary" data-delete-provider="${esc(p.id)}">Delete</button><button class="secondary" data-apply-provider="${esc(p.id)}">Apply profile</button></div></div>`).join("") || empty("No saved provider profiles")}<small>Profiles update shared OpenCode config and preserve native logins. Configure the native server bridge to apply live; otherwise restart OpenCode after applying. <a href="https://github.com/newrecycle/Dark-Moon/blob/pro/docs/opencode-webui.md" target="_blank" rel="noopener noreferrer">Set up native sign-in</a>.</small></section><section class="panel"><div class="section-top"><div><h3>Installation health</h3><p>Inspect dependencies, paths and the operator-controlled integrity guard.</p></div><div><button class="secondary" data-doctor="1">Run diagnostics</button> <button class="secondary" data-updates="1">Check image updates</button></div></div><p class="instructions">Enforcement is opt-in. After reviewing your source and Compose policy, create the integrity baseline with the documented local command. Licensing and vendor activation are not part of this independent implementation.</p></section>`;
    }
  };
  async function providerForm(
    kind = "provider",
    profile = null,
    duplicate = false,
  ) {
    await loadChoices();
    const providers = [
      ...(choices.opencode?.providers || []).map((p) => ({
        value: p.id,
        label: `${p.name}${p.connected ? " — connected" : ""}`,
      })),
      { value: "__custom__", label: "Custom provider…" },
    ];
    const specs = [
      ["name", "Profile name (optional)"],
      ["provider", "Provider", "select", providers],
      ["custom_provider", "Custom provider id"],
      ["mode", "Protocol / mode", "select", ["cloud", "local", "anthropic"]],
      ["model", "Model", "select", []],
      ["custom_model", "Custom model id"],
      ["base_url", "Base URL (optional for built-in providers)"],
      [
        "credential_id",
        "Saved API key (optional when connected)",
        "select",
        credentials("provider_api_key"),
      ],
    ];
    openForm(
      kind,
      profile
        ? duplicate
          ? "Duplicate provider profile"
          : "Edit provider profile"
        : "Choose OpenCode provider and model",
      specs,
      {
        profileId: profile && !duplicate ? profile.id : null,
        models: profile?.models || [],
      },
    );
    const f = $("#workspace-form"),
      pid = profile?.provider || choices.opencode?.active_model?.split("/")[0];
    f.elements.provider.value = providers.some((p) => p.value === pid)
      ? pid
      : "__custom__";
    providerModels();
    if (profile) {
      f.elements.name.value = duplicate
        ? (profile.name || profile.provider) + " (copy)"
        : profile.name || "";
      if (f.elements.provider.value === "__custom__")
        f.elements.custom_provider.value = profile.provider;
      if (profile.models?.length)
        f.elements.model.innerHTML = optionsHtml([
          ...profile.models.map((m) => ({ value: m.id, label: m.name })),
          { value: "__custom__", label: "Custom model…" },
        ]);
      const model = profile.model.startsWith(pid + "/")
        ? profile.model.slice(pid.length + 1)
        : profile.model;
      if ([...f.elements.model.options].some((o) => o.value === model))
        f.elements.model.value = model;
      else {
        f.elements.model.value = "__custom__";
        f.elements.custom_model.value = model;
      }
      for (const key of ["mode", "base_url", "credential_id"])
        f.elements[key].value = profile[key] || "";
      customFields();
    }
    $("#workspace-fields").insertAdjacentHTML(
      "beforeend",
      '<button class="secondary" type="button" data-discover-models="1">Discover endpoint models</button><p class="instructions">Queries the selected endpoint’s model list using the chosen saved key. No inference request is sent.</p><p id="model-discovery-status" role="status"></p>',
    );
  }
  function providerValues(form) {
    const raw = Object.fromEntries(new FormData(form));
    if (raw.provider === "__custom__") raw.provider = raw.custom_provider;
    if (raw.model === "__custom__") raw.model = raw.custom_model;
    delete raw.custom_provider;
    delete raw.custom_model;
    return raw;
  }
  function markdownPreview(markdown) {
    // Decode Markdown character references only into text nodes, never HTML.
    const literal = value => value.replace(/&(amp|lt|gt);/g, (_, key) => ({amp:"&",lt:"<",gt:">"})[key]);
    const cells = line => {
      const result = []; let value = "";
      for (let i = 1; i < line.length - 1; i++) {
        if (line[i] === "\\" && line[i + 1] === "|") { value += "|"; i++; }
        else if (line[i] === "|") { result.push(value); value = ""; }
        else value += line[i];
      }
      result.push(value);
      return result;
    };
    const root = document.createElement("div");
    root.className = "report-preview";
    let code = null, fence = 0,
      table = null;
    for (const line of markdown.split("\n")) {
      const marker = line.match(/^(`{3,})([^`]*)$/);
      if (marker && (!code || (marker[1].length >= fence && !marker[2].trim()))) {
        if (code) {
          code = null;
          fence = 0;
        } else {
          fence = marker[1].length;
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
        h.textContent = literal(heading[2]);
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
        for (const cell of cells(line)) {
          const td = document.createElement("td");
          td.textContent = literal(cell.trim().replaceAll("**", "").replaceAll("`", ""));
          tr.append(td);
        }
        table.append(tr);
        continue;
      }
      table = null;
      if (line.trim()) {
        const p = document.createElement("p");
        p.textContent = literal(line);
        root.append(p);
      }
    }
    const headings = [...root.querySelectorAll("h1,h2")];
    if (headings.length) {
      const navigation = document.createElement("nav");
      navigation.className = "report-sections";
      navigation.setAttribute("aria-label", "Report sections");
      for (const [index, heading] of headings.entries()) {
        heading.id = `report-section-${index}`;
        heading.tabIndex = -1;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary";
        button.textContent = heading.textContent;
        button.setAttribute("aria-controls", heading.id);
        button.addEventListener("click", () => {
          heading.scrollIntoView({block: "start"});
          heading.focus({preventScroll: true});
        });
        navigation.append(button);
      }
      root.prepend(navigation);
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
      if (button.dataset.editProvider || button.dataset.copyProvider) {
        const id = button.dataset.editProvider || button.dataset.copyProvider;
        const r = await api(
          `/api/v1/system/providers/${encodeURIComponent(id)}`,
        );
        await providerForm(
          "provider",
          r.data,
          Boolean(button.dataset.copyProvider),
        );
      }
      if (button.dataset.deleteProvider) {
        const r = await api(
          `/api/v1/system/providers/${encodeURIComponent(button.dataset.deleteProvider)}`,
        );
        openForm("provider_delete", "Delete saved profile", [], {
          profileId: r.data.id,
        });
        $("#workspace-fields").innerHTML =
          `<p>Remove ${esc(r.data.name || r.data.provider)}? Your active OpenCode model and provider login will be retained.</p>`;
      }
      if (button.dataset.checkProvider) {
        button.disabled = true;
        try {
          const r = await api(
            `/api/v1/system/providers/${encodeURIComponent(button.dataset.checkProvider)}/check`,
            { method: "POST", body: "{}" },
          );
          await window.renderWorkspace("settings");
          details(
            "Provider check",
            `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`,
          );
        } finally {
          button.disabled = false;
        }
      }
      if (button.dataset.bridgeHealth) {
        const r = await api("/api/v1/system/opencode-health");
        details(
          "OpenCode bridge health",
          `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`,
        );
      }
      if (button.dataset.discoverModels) {
        const requestedForm = formState;
        button.disabled = true;
        try {
          const r = await api("/api/v1/system/provider-models", {
            method: "POST",
            body: JSON.stringify(providerValues($("#workspace-form"))),
          });
          if (formState !== requestedForm || !$("#workspace-dialog").open)
            return;
          const f = $("#workspace-form"),
            previous = f.elements.model.value;
          formState.models = r.models;
          f.elements.model.innerHTML = optionsHtml([
            ...r.models.map((m) => ({ value: m.id, label: m.name })),
            { value: "__custom__", label: "Custom model…" },
          ]);
          if (r.models.some((m) => m.id === previous))
            f.elements.model.value = previous;
          customFields();
          $("#model-discovery-status").textContent =
            `${r.models.length} models found${r.truncated ? " (list truncated)" : ""} · ${r.latency_ms} ms. ${r.note}`;
        } catch (error) {
          if (formState === requestedForm && $("#model-discovery-status"))
            $("#model-discovery-status").textContent = error.message;
        } finally {
          button.disabled = false;
        }
      }

      if (button.dataset.sourceFiles) await loadSourceFiles();
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
      if (action === "credential") {
        const catalog = await api("/api/v1/credentials/providers");
        openForm("credential", "Store encrypted credential", [
          ["name", "Name"],
          ["provider", "Credential use (descriptive label)", "select",
            catalog.data.map((p) => ({ value: p.id, label: p.name }))],
          ["username", "Username (optional; required for target login)"],
          ["secret", "Secret", "password"],
        ]);
      }
      if (action === "webhook")
        openForm("webhook", "Register webhook", [
          ["url", "HTTPS receiver URL"],
          [
            "events",
            "Events (choose one or more)",
            "multiple",
            [
              "*",
              "campaign.started",
              "campaign.completed",
              "campaign.aborted",
              "finding.discovered",
              "finding.confirmed",
              "finding.exploited",
              "retest.completed",
              "remediation.updated",
              "pr.opened",
              "pr.updated",
            ],
          ],
          ["secret", "Signing secret (at least 24 characters)", "password"],
        ]);
      if (action === "provider") await providerForm();
      if (action === "opencode_connect") {
        await loadChoices();
        const providers = [
          ...(choices.opencode?.providers || []).map((p) => ({
            value: p.id,
            label: `${p.name}${p.connected ? " — connected" : ""}`,
          })),
          { value: "__custom__", label: "Custom provider…" },
        ];
        const specs = [
          ["provider", "Provider", "select", providers],
          ["custom_provider", "Custom provider id"],
        ];
        specs.push(
          ["auth_method", "Login method", "select", []],
          [
            "credential_id",
            "Saved API key (optional)",
            "select",
            credentials("provider_api_key"),
          ],
          ["secret", "New API key (optional)", "password"],
        );
        openForm(
          action,
          action === "provider"
            ? "Choose OpenCode provider and model"
            : "Connect OpenCode provider",
          specs,
        );
        const active = choices.opencode?.active_model?.split("/")[0];
        if (providers.some((p) => p.value === active))
          $("#workspace-form").elements.provider.value = active;
        providerModels();
      }
      if (action === "project")
        openForm("project", "Create project", [
          ["name", "Project name"],
          ["description", "Description", "textarea"],
        ]);
      if (action === "retest") {
        await loadChoices();
        if (!choices.campaigns.length)
          throw new Error("Create an assessment before requesting a retest.");
        openForm("retest", "Retest an assessment", [
          [
            "campaign_id",
            "Base assessment",
            "select",
            choices.campaigns.map((c) => ({
              value: c.id,
              label: c.name || c.id,
            })),
          ],
          ["finding_ids", "Findings (optional)", "multiple", []],
        ]);
        retestFindings();
      }
      if (button.dataset.disconnectOpencode) {
        const r = await api("/api/v1/system/opencode/disconnect", {
          method: "POST",
          body: JSON.stringify({ provider: button.dataset.disconnectOpencode }),
        });
        await window.renderWorkspace("settings");
        details(
          "OpenCode login removed",
          `<p>${esc(r.restart_required ? "Shared login removed. Restart OpenCode to finish disconnecting." : "Provider disconnected.")}</p>${r.warning ? `<p>${esc(r.warning)}</p>` : ""}`,
        );
      }
      if (button.dataset.syncOpencode) {
        await api("/api/v1/system/opencode/sync", {
          method: "POST",
          body: "{}",
        });
        await window.renderWorkspace("settings");
      }
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
        const cid = button.dataset.reportPreview, previousToken = token;
        details("Assessment report", '<p role="status">Loading report…</p>');
        $("#detail-body").dataset.pendingReport = cid;
        const version = evidenceViewVersion;
        const current = () => $("#detail").open && token === previousToken && version === evidenceViewVersion;
        if (identity?.role === "admin") {
          try {
            const started = Date.now();
            const grant = await api("/api/v1/evidence/grants", {
              method:"POST",body:JSON.stringify({kind:"report",id:cid})
            });
            if (!current()) return;
            const until = started + Math.min(45, Number(grant.expires_in) || 0) * 1000;
            const response = await api(`/api/v1/evidence/report/${encodeURIComponent(cid)}/reveal`, {
              headers: {"X-Darkmoon-Evidence-Grant": grant.grant}
            });
            if (!current()) return;
            if (Date.now() >= until) {
              delete $("#detail-body").dataset.pendingReport;
              $("#detail-body").textContent = "Report preview expired. Close and preview again to refresh access.";
              return;
            }
            if (typeof response.data?.content !== "string") throw new Error("Report unavailable");
            delete $("#detail-body").dataset.pendingReport;
            $("#detail-body").replaceChildren();
            const output = document.createElement("section");
            output.dataset.revealedContent = "true";
            output.dataset.reportCampaign = cid;
            if (response.data.content.trim()) output.append(markdownPreview(response.data.content));
            else output.textContent = "No report content recorded.";
            $("#detail-body").append(output);
            setTimeout(() => {
              if (current()) {
                clearRevealedContent();
                $("#detail-body").textContent = "Report preview expired. Close and preview again to refresh access.";
              }
            }, Math.max(0, until - Date.now()));
          } catch (error) {
            if (current()) {
              delete $("#detail-body").dataset.pendingReport;
              $("#detail-body").textContent = "Report unavailable. Close and preview again to retry.";
            }
          }
        } else {
          delete $("#detail-body").dataset.pendingReport;
          $("#detail-body").textContent = "Administrator access is required to preview recorded evidence.";
        }
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
      if (button.dataset.detailCredential) {
        const r = await api(
          `/api/v1/credentials/${encodeURIComponent(button.dataset.detailCredential)}`,
        );
        details("Masked credential metadata", `<pre>${esc(JSON.stringify(r.data, null, 2))}</pre>`);
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
        details(
          r.warning
            ? "Provider saved; live update failed"
            : "Provider settings saved",
          `<p>${esc(r.note)}</p>${r.warning ? `<p role="alert">${esc(r.warning)}</p>` : ""}`,
        );
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
    const context = formState, previousToken = token;
    const current = () => formState === context && token === previousToken && $("#workspace-dialog").open;
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
      if (kind === "provider_delete")
        result = await api(
          `/api/v1/system/providers/${encodeURIComponent(formState.profileId)}`,
          { method: "DELETE" },
        );
      if (kind === "provider") {
        const values = providerValues(event.target);
        values.models = formState.models || [];
        const id = formState.profileId;
        result = await api(
          id
            ? `/api/v1/system/providers/${encodeURIComponent(id)}`
            : "/api/v1/system/providers",
          { method: id ? "PATCH" : "POST", body: JSON.stringify(values) },
        );
      }
      if (kind === "opencode_connect") {
        if (raw.provider === "__custom__") raw.provider = raw.custom_provider;
        if (raw.auth_method !== "api") {
          result = await api("/api/v1/system/opencode/oauth-start", {
            method: "POST",
            body: JSON.stringify({
              provider: raw.provider,
              method: Number(raw.auth_method),
            }),
          });
          openForm(
            "opencode_oauth",
            "Finish OpenCode sign-in",
            [["code", "Authorization code (optional for automatic login)"]],
            { provider: raw.provider, method: Number(raw.auth_method) },
          );
          $("#workspace-fields").insertAdjacentHTML(
            "afterbegin",
            `<p><a href="${esc(result.url)}" target="_blank" rel="noopener noreferrer">Continue with provider →</a></p><p>${esc(result.instructions)}</p>`,
          );
          return;
        }
        if (!raw.credential_id) {
          if (!raw.secret)
            throw new Error("Choose a saved key or enter a new API key.");
          const key = await api("/api/v1/credentials", {
            method: "POST",
            body: JSON.stringify({
              name: `OpenCode: ${raw.provider}`,
              provider: raw.provider,
              secret: raw.secret,
            }),
          });
          raw.credential_id = key.data.id;
        }
        result = await api("/api/v1/system/opencode/connect", {
          method: "POST",
          body: JSON.stringify({
            provider: raw.provider,
            credential_id: raw.credential_id,
          }),
        });
      }
      if (kind === "opencode_oauth")
        result = await api("/api/v1/system/opencode/oauth-finish", {
          method: "POST",
          body: JSON.stringify({
            provider: formState.provider,
            method: formState.method,
            code: raw.code,
          }),
        });
      if (kind === "opencode_oauth" && !result.connected)
        throw new Error(
          "OpenCode has not completed sign-in yet. Complete the provider approval and retry.",
        );
      if (kind === "project")
        result = await api("/api/v1/projects", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      if (kind === "webhook") {
        raw.events = new FormData(event.target)
          .getAll("events")
          .filter(Boolean);
        result = await api("/api/v1/webhooks", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      }
      if (kind === "retest") {
        raw.finding_ids = new FormData(event.target)
          .getAll("finding_ids")
          .filter(Boolean);
        result = await api("/api/v1/retest", {
          method: "POST",
          body: JSON.stringify(raw),
        });
      }
      if (kind === "protected_pdf") {
        const cid = context.campaignId;
        const grant = await api("/api/v1/evidence/grants", {
          method:"POST",body:JSON.stringify({kind:"report_pdf",id:cid})
        });
        if (!current()) return;
        const res = await fetch(
          `/api/v1/campaigns/${encodeURIComponent(cid)}/report/pdf`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${previousToken}`,
              "Content-Type": "application/json",
              "X-Darkmoon-Evidence-Grant": grant.grant,
            },
            body: JSON.stringify({ password: raw.password, sign: true }),
          },
        );
        if (!res.ok) throw new Error("Protected report export unavailable. Retry from the assessment.");
        const body = await res.blob();
        if (!current()) return;
        const url = URL.createObjectURL(body),
          a = document.createElement("a");
        a.href = url;
        a.download = `${cid}-protected.pdf`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      if (!current()) return;
      $("#workspace-dialog").close();
      await refresh();
      if (kind === "opencode_connect")
        details(
          "Provider login saved",
          `<p>${esc(result.restart_required ? "Shared login saved. Restart OpenCode to load it." : "Provider connected in OpenCode.")}</p>${result.warning ? `<p>${esc(result.warning)}</p>` : ""}`,
        );
    } catch (error) {
      if (current()) $("#workspace-error").textContent = error.message;
    } finally {
      if (formState === context || formState === null) button.disabled = false;
    }
  });
  $("#workspace-dialog").addEventListener("close", () => {
    formState = null;
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
