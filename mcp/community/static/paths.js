"use strict";

window.setupRecordedPaths = ({graph, cid, signal, card, stopLocationTour, highlight, selectStep}) => {
  const root = $("#recorded-paths"), editable = identity?.role !== "viewer";
  const url = `/api/v1/campaigns/${encodeURIComponent(cid)}`;
  let paths = graph.paths || [], playback = null, sequence = 0, draft = [], editing = null, historyRequest = 0, editorRequest = 0;
  const publicGraph = graph;
  const opaquePath = ({id,campaign_id,version}) => ({id,campaign_id,version});
  let publicPaths = (publicGraph.paths || []).map(opaquePath);
  let revealUntil = 0, revealControl = null, revealTimer;
  const revealed = () => revealUntil > Date.now() && Boolean(revealControl) && !revealControl.signal.aborted;
  async function scopedRequest(path, options = {}) {
    if (!revealed()) throw new Error("Reveal the path review before accessing its content");
    const currentToken = token, control = revealControl;
    const requestSignal = AbortSignal.any([signal, control.signal]);
    const issued = await api("/api/v1/evidence/grants", {method:"POST",signal:requestSignal,
      body:JSON.stringify({kind:"graph",id:cid,campaign_id:cid})});
    if (!revealed() || currentToken !== token || control !== revealControl) throw new Error("Review session changed");
    const value = await api(path, {...options,signal:requestSignal,
      headers:{"X-Darkmoon-Evidence-Grant":issued.grant}});
    if (!revealed() || currentToken !== token || control !== revealControl) throw new Error("Review session changed");
    return value;
  }
  function clearReview(selected = "") {
    clearTimeout(revealTimer); revealUntil = 0; revealControl?.abort(); revealControl = null;
    graph = publicGraph; paths = publicPaths; draft = [];
    edges = graph.edges.filter(e => e.kind === "observed" && e.source !== e.target);
    stop(false); card.replaceChildren();
    if (!signal.aborted) {paint(selected); status("Review content cleared. Authorize a new reveal to continue.");}
    else root.replaceChildren();
  }
  async function revealReview() {
    const selected = selectedPath()?.id || "";
    if (identity?.role !== "admin" || !document.hasFocus() || document.hidden) return;
    clearTimeout(revealTimer); revealControl?.abort(); revealControl = new AbortController();
    revealUntil = Date.now() + 45000;
    const control = revealControl;
    revealTimer = setTimeout(() => clearReview(selectedPath()?.id || ""), 45000);
    status("Loading a scoped review reveal…");
    try {
      const result = await scopedRequest(`/api/v1/evidence/graph/${encodeURIComponent(cid)}/reveal`);
      if (result.data?.campaign_id !== cid) throw new Error("Graph scope mismatch");
      graph = result.data; paths = graph.paths || [];
      edges = graph.edges.filter(e => e.kind === "observed" && e.source !== e.target);
      paint(selected); status("Review revealed for at most 45 seconds. Focus, view or path selection changes clear it.");
    } catch (error) {
      if (!signal.aborted && revealed() && control === revealControl) {clearReview(selected); status(`Review unavailable: ${error.message}`);}
    }
  }
  const nodeName = id => graph.nodes.find(n => n.id === id)?.label || id;
  let edges = graph.edges.filter(e => e.kind === "observed" && e.source !== e.target);
  const hasContent = value => Array.isArray(value) ? value.some(hasContent)
    : value && typeof value === "object" ? Object.values(value).some(hasContent)
    : typeof value === "string" ? Boolean(value.trim()) : value !== undefined && value !== null;
  const evidencePresent = f => f.evidence_meta?.has_evidence === true || f.has_evidence === true ||
    [f.evidence, f.evidence_output, f.evidence_commands].some(hasContent);
  const candidates = edge => graph.findings.filter(f =>
    ["confirmed", "exploited", "remediated", "resolved"].includes(f.status) && evidencePresent(f) &&
    [edge.source, edge.target].some(id => f.node_id === id || f.infra_node_id === id));
  function stop(focus = true) {
    sequence++;
    playback = null;
    card.hidden = true;
    highlight("");
    const play = root.querySelector("#path-play");
    if (focus && play) play.focus();
  }
  function status(message) { root.querySelector("#path-status").textContent = message; }
  function selectedPath() { return paths.find(p => p.id === root.querySelector("#path-select").value); }
  function updateActions() {
    const path = selectedPath();
    root.querySelector("#path-play").disabled = !revealed() || !path?.valid;
    const remove = root.querySelector("#path-delete");
    if (remove) remove.disabled = !revealed() || !path;
    for (const id of ["path-edit", "path-history-open"]) {
      const button = root.querySelector("#" + id); if (button) button.disabled = !revealed() || !path;
    }
    status(path ? path.valid ? "References and evidence match the current records." : `Unavailable: ${(path.issues || ["Reveal the review to check its references."]).join(" ")}` : "No path selected. Finding-location tours remain available above.");
  }
  async function showStep(index) {
    const pathId = playback?.id, version = playback?.version;
    if (!pathId) return;
    const request = ++sequence;
    status("Checking current evidence…");
    try {
      const current = (await scopedRequest(`/api/v1/evidence/graph/${encodeURIComponent(cid)}/reveal`)).data;
      if (signal.aborted || request !== sequence) return;
      paths = current.paths;
      const path = current.paths.find(p => p.id === pathId);
      if (!path?.valid) throw new Error(path ? (path.issues || ["References unavailable"]).join(" ") : "Recorded path was deleted");
      if ((path.version || 1) !== version) throw new Error("Recorded path changed; restart the tour to review its new revision");
      const step = path.steps[index], edge = current.edges.find(e => e.id === step.edge_id);
      if (!edge) throw new Error("Recorded connection is unavailable");
      playback = {id:pathId, index, version};
      selectStep(edge);
      highlight(edge.id);
      const source = current.nodes.find(n => n.id === edge.source), target = current.nodes.find(n => n.id === edge.target);
      card.hidden = false;
      card.innerHTML = `<p role="status">Recorded path · Step ${index + 1} of ${path.steps.length}</p><h3>${esc(path.title)}</h3><p>${esc(source?.label || edge.source)} → ${esc(target?.label || edge.target)}</p><details><summary>Technical details</summary><p class="detail-text">${esc(step.rationale)}</p><p>Supporting finding: ${esc(step.finding_id)}</p><button class="secondary" data-finding="${esc(step.finding_id)}" data-cid="${esc(cid)}">Open supporting evidence</button></details><p class="instructions">Operator-reviewed connections and evidence. This record does not independently verify an exploit chain.</p><div class="toolbar"><button class="secondary" id="path-back" ${index === 0 ? "disabled" : ""}>Back</button><button class="secondary" id="path-next">${index === path.steps.length - 1 ? "Finish" : "Next"}</button><button class="secondary" id="path-free">Explore freely</button></div>`;
      $("#path-back").addEventListener("click", () => showStep(index - 1), {signal});
      $("#path-next").addEventListener("click", () => index === path.steps.length - 1 ? stop() : showStep(index + 1), {signal});
      $("#path-free").addEventListener("click", () => stop(), {signal});
      $("#path-free").focus();
      status(`Showing step ${index + 1}; evidence checked before this step.`);
    } catch (error) {
      if (signal.aborted || request !== sequence) return;
      stop(false);
      updateActions();
      status(`Path unavailable: ${error.message}`);
      root.querySelector("#path-play").focus();
    }
  }
  function renderSteps() {
    const container = root.querySelector("#path-draft");
    container.innerHTML = draft.map((step, index) => {
      const previous = index ? edges.find(e => e.id === draft[index - 1].edge_id)?.target : null;
      const options = edges.filter(e => (!previous || e.source === previous) && !draft.slice(0,index).some(s => s.edge_id === e.id));
      const edge = edges.find(e => e.id === step.edge_id);
      return `<fieldset><legend>Step ${index + 1}</legend><label>Recorded connection<select data-path-edge="${index}" required><option value="">Choose connection</option>${options.map(e => `<option value="${esc(e.id)}" ${step.edge_id === e.id ? "selected" : ""}>${esc(nodeName(e.source))} → ${esc(nodeName(e.target))}</option>`).join("")}</select></label><label>Supporting finding<select data-path-finding="${index}" required><option value="">Choose finding with evidence</option>${(edge ? candidates(edge) : []).map(f => `<option value="${esc(f.id)}" ${step.finding_id === f.id ? "selected" : ""}>${esc(f.title || f.id)}</option>`).join("")}</select></label><label>How does this evidence support the connection?<textarea data-path-rationale="${index}" maxlength="4000" required>${esc(step.rationale)}</textarea></label></fieldset>`;
    }).join("");
    root.querySelector("#path-remove-step").disabled = !draft.length;
    root.querySelector("#path-add-step").disabled = draft.length >= 32;
  }
  function resetEditor() {
    editing = null; editorRequest++;
    const form = root.querySelector("#path-form");
    if (!form) return;
    form.reset(); draft = [{edge_id:"",finding_id:"",rationale:""}]; renderSteps();
    form.querySelector('[type="submit"]').disabled = false;
    root.querySelector("#path-editor summary").textContent = "Record an evidence-backed path";
    root.querySelector("#path-new").hidden = true;
    root.querySelector("#path-save-status").textContent = "";
  }
  function beginEdit() {
    const path = selectedPath(), form = root.querySelector("#path-form");
    if (!revealed() || !path || !form) return;
    stop(false); editorRequest++;
    editing = {id:path.id, version:path.version || 1};
    draft = path.steps.map(({edge_id,finding_id,rationale}) => ({edge_id,finding_id,rationale}));
    form.elements.title.value = path.title; form.elements.reviewed.checked = false;
    form.querySelector('[type="submit"]').disabled = false;
    root.querySelector("#path-editor").open = true;
    root.querySelector("#path-editor summary").textContent = `Edit path · revision ${editing.version}`;
    root.querySelector("#path-new").hidden = false;
    root.querySelector("#path-save-status").textContent = "Review the current evidence before saving a new immutable revision.";
    renderSteps(); form.elements.title.focus();
  }
  async function showHistory() {
    const path = selectedPath(); if (!path) return;
    const request = ++historyRequest, target = root.querySelector("#path-history");
    target.textContent = "Loading revision history…";
    try {
      const result = await scopedRequest(`${url}/paths/${encodeURIComponent(path.id)}/revisions`);
      if (signal.aborted || request !== historyRequest || selectedPath()?.id !== path.id) return;
      target.innerHTML = `<h4>Immutable review history</h4><p>Historical annotations; playback always checks the current revision and evidence.</p>` +
        result.data.map(row => `<details data-path-revision="${esc(row.version)}"><summary>Revision ${esc(row.version)} · ${esc(row.title)}${row.version === result.current_version ? " · current" : ""}</summary><p>Reviewed by ${esc(row.reviewed_by || row.recorded_by)} · ${esc(row.updated_at || row.created_at)}</p><ol>${row.steps.map(step => `<li>${esc(step.finding_id)}: ${esc(step.rationale)}</li>`).join("")}</ol></details>`).join("");
    } catch (error) {
      if (!signal.aborted && request === historyRequest) target.textContent = `History unavailable: ${error.message}`;
    }
  }
  function paint(selected = "") {
    historyRequest++; editorRequest++; editing = null;
    root.innerHTML = `<h3>Recorded paths</h3>${identity?.role === "admin" ? '<button class="secondary" id="path-reveal">Reveal graph and path reviews (45 seconds)</button>' : '<p>Administrator reveal is required to inspect review content.</p>'}<p class="instructions">Save ordered connections with supporting finding evidence and your review rationale. Containment lines alone cannot become a path.</p><div class="toolbar"><label for="path-select">Path</label><select id="path-select"><option value="">Choose a recorded path</option>${paths.map(p => `<option value="${esc(p.id)}" ${p.id === selected ? "selected" : ""}>${esc(p.title || p.id)}${p.valid ? "" : " · needs review"}</option>`).join("")}</select><button class="secondary" id="path-play" disabled>Tour recorded path</button>${editable ? '<button class="secondary" id="path-edit" disabled>Edit reviewed path</button><button class="secondary" id="path-delete" disabled>Delete path</button>' : ""}<button class="secondary" id="path-history-open" disabled>Revision history</button></div><p id="path-status" role="status"></p><section id="path-history" aria-live="polite"></section>${editable && revealed() ? `<details id="path-editor"><summary>Record an evidence-backed path</summary>${edges.length ? `<form id="path-form"><label>Path title<input name="title" maxlength="160" required></label><div id="path-draft"></div><div class="toolbar"><button type="button" class="secondary" id="path-add-step">Add step</button><button type="button" class="secondary" id="path-remove-step">Remove last step</button></div><label class="path-review"><input type="checkbox" name="reviewed" required> I reviewed the evidence for each connection and recorded its limitations.</label><button type="submit" class="primary">Save reviewed path</button><button type="button" class="secondary" id="path-new" hidden>Cancel edit / new path</button><p id="path-save-status" role="status"></p></form>` : '<p>No recorded directed connections are available. Record connection and finding evidence before creating a path.</p>'}</details>` : ""}`;
    root.querySelector("#path-select").addEventListener("change", () => {
      const selected = root.querySelector("#path-select").value;
      if (revealed()) {clearReview(selected); return;}
      stop(false); historyRequest++; root.querySelector("#path-history").replaceChildren(); resetEditor(); updateActions();
    }, {signal});
    root.querySelector("#path-reveal")?.addEventListener("click", revealReview, {signal});
    root.querySelector("#path-play").addEventListener("click", () => {
      const path = selectedPath();
      if (!revealed() || !path?.valid) return;
      stopLocationTour();
      playback = {id:path.id, index:0, version:path.version || 1};
      showStep(0);
    }, {signal});
    root.querySelector("#path-delete")?.addEventListener("click", async () => {
      const path = selectedPath(); if (!path) return;
      try {
        await scopedRequest(`${url}/paths/${encodeURIComponent(path.id)}`, {method:"DELETE"});
        if (signal.aborted) return;
        stop(false); paths = paths.filter(p => p.id !== path.id); publicPaths = publicPaths.filter(p => p.id !== path.id); paint(); status("Recorded path deleted.");
      } catch (error) {if (!signal.aborted) status(error.message);}
    }, {signal});
    root.querySelector("#path-edit")?.addEventListener("click", beginEdit, {signal});
    root.querySelector("#path-history-open").addEventListener("click", showHistory, {signal});
    root.querySelector("#path-new")?.addEventListener("click", resetEditor, {signal});
    const form = root.querySelector("#path-form");
    if (form) {
      draft = [{edge_id:"", finding_id:"", rationale:""}]; renderSteps();
      root.querySelector("#path-add-step").addEventListener("click", () => {draft.push({edge_id:"",finding_id:"",rationale:""});renderSteps();}, {signal});
      root.querySelector("#path-remove-step").addEventListener("click", () => {draft.pop();renderSteps();}, {signal});
      form.addEventListener("input", event => {
        const d = event.target.dataset;
        if (d.pathRationale !== undefined) draft[Number(d.pathRationale)].rationale = event.target.value;
        if (d.pathFinding !== undefined) draft[Number(d.pathFinding)].finding_id = event.target.value;
      }, {signal});
      form.addEventListener("change", event => {
        const index = event.target.dataset.pathEdge;
        if (index !== undefined) {
          draft[Number(index)].edge_id = event.target.value; draft[Number(index)].finding_id = "";
          draft.splice(Number(index) + 1); renderSteps();
        }
      }, {signal});
      form.addEventListener("submit", async event => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        const currentEdit = editing, request = ++editorRequest;
        const body = {title:form.elements.title.value,steps:draft,reviewed:form.elements.reviewed.checked};
        if (currentEdit) body.version = currentEdit.version;
        try {
          const result = await scopedRequest(url + "/paths" + (currentEdit ? "/" + encodeURIComponent(currentEdit.id) : ""),
            {method:currentEdit ? "PUT" : "POST",signal,body:JSON.stringify(body)});
          if (signal.aborted || request !== editorRequest) return;
          stop(false); paths = paths.filter(path => path.id !== result.data.id); paths.push(result.data);
          publicPaths = publicPaths.filter(path => path.id !== result.data.id); publicPaths.push(opaquePath(result.data));
          paint(result.data.id); status(currentEdit ? `Reviewed path updated to revision ${result.data.version}.` : "Reviewed path saved. Select Tour recorded path to inspect each step.");
        } catch (error) {if (!signal.aborted && request === editorRequest) {root.querySelector("#path-save-status").textContent = error.message;button.disabled = false;}}
      }, {signal});
    }
    updateActions();
  }
  window.addEventListener("blur", () => {if (revealed()) clearReview(selectedPath()?.id || "");}, {signal});
  document.addEventListener("visibilitychange", () => {if (document.hidden && revealed()) clearReview(selectedPath()?.id || "");}, {signal});
  signal.addEventListener("abort", () => clearReview(), {once:true});
  paint();
  return {stop};
};
