"use strict";

window.setupRecordedPaths = ({graph, cid, signal, card, stopLocationTour, highlight, selectStep}) => {
  const root = $("#recorded-paths"), editable = identity?.role !== "viewer";
  const url = `/api/v1/campaigns/${encodeURIComponent(cid)}`;
  let paths = graph.paths || [], playback = null, sequence = 0, draft = [];
  const nodeName = id => graph.nodes.find(n => n.id === id)?.label || id;
  const edges = graph.edges.filter(e => e.kind === "observed" && e.source !== e.target);
  const hasContent = value => Array.isArray(value) ? value.some(hasContent)
    : value && typeof value === "object" ? Object.values(value).some(hasContent)
    : typeof value === "string" ? Boolean(value.trim()) : value !== undefined && value !== null;
  const evidencePresent = f => [f.evidence, f.evidence_output, f.evidence_commands].some(hasContent);
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
    root.querySelector("#path-play").disabled = !path?.valid;
    const remove = root.querySelector("#path-delete");
    if (remove) remove.disabled = !path;
    status(path ? path.valid ? "References and evidence match the current records." : `Unavailable: ${path.issues.join(" ")}` : "No path selected. Finding-location tours remain available above.");
  }
  async function showStep(index) {
    const pathId = playback?.id;
    if (!pathId) return;
    const request = ++sequence;
    status("Checking current evidence…");
    try {
      const current = await api(url + "/graph", {signal});
      if (signal.aborted || request !== sequence) return;
      paths = current.paths;
      const path = current.paths.find(p => p.id === pathId);
      if (!path?.valid) throw new Error(path ? path.issues.join(" ") : "Recorded path was deleted");
      const step = path.steps[index], edge = current.edges.find(e => e.id === step.edge_id);
      if (!edge) throw new Error("Recorded connection is unavailable");
      playback = {id:pathId, index};
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
  function paint(selected = "") {
    root.innerHTML = `<h3>Recorded paths</h3><p class="instructions">Save ordered connections with supporting finding evidence and your review rationale. Containment lines alone cannot become a path.</p><div class="toolbar"><label for="path-select">Path</label><select id="path-select"><option value="">Choose a recorded path</option>${paths.map(p => `<option value="${esc(p.id)}" ${p.id === selected ? "selected" : ""}>${esc(p.title)}${p.valid ? "" : " · needs review"}</option>`).join("")}</select><button class="secondary" id="path-play" disabled>Tour recorded path</button>${editable ? '<button class="secondary" id="path-delete" disabled>Delete path</button>' : ""}</div><p id="path-status" role="status"></p>${editable ? `<details id="path-editor"><summary>Record an evidence-backed path</summary>${edges.length ? `<form id="path-form"><label>Path title<input name="title" maxlength="160" required></label><div id="path-draft"></div><div class="toolbar"><button type="button" class="secondary" id="path-add-step">Add step</button><button type="button" class="secondary" id="path-remove-step">Remove last step</button></div><label class="path-review"><input type="checkbox" name="reviewed" required> I reviewed the evidence for each connection and recorded its limitations.</label><button type="submit" class="primary">Save reviewed path</button><p id="path-save-status" role="status"></p></form>` : '<p>No recorded directed connections are available. Record connection and finding evidence before creating a path.</p>'}</details>` : ""}`;
    root.querySelector("#path-select").addEventListener("change", () => {stop(false); updateActions();}, {signal});
    root.querySelector("#path-play").addEventListener("click", () => {
      const path = selectedPath();
      if (!path?.valid) return;
      stopLocationTour();
      playback = {id:path.id, index:0};
      showStep(0);
    }, {signal});
    root.querySelector("#path-delete")?.addEventListener("click", async () => {
      const path = selectedPath(); if (!path) return;
      try {
        await api(`${url}/paths/${encodeURIComponent(path.id)}`, {method:"DELETE",signal});
        if (signal.aborted) return;
        stop(false); paths = paths.filter(p => p.id !== path.id); paint(); status("Recorded path deleted.");
      } catch (error) {if (!signal.aborted) status(error.message);}
    }, {signal});
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
        try {
          const result = await api(url + "/paths", {method:"POST",signal,body:JSON.stringify({title:form.elements.title.value,steps:draft,reviewed:form.elements.reviewed.checked})});
          if (signal.aborted) return;
          stop(false); paths.push(result.data); paint(result.data.id); status("Reviewed path saved. Select Tour recorded path to inspect each step.");
        } catch (error) {if (!signal.aborted) {root.querySelector("#path-save-status").textContent = error.message;button.disabled = false;}}
      }, {signal});
    }
    updateActions();
  }
  signal.addEventListener("abort", () => stop(false), {once:true});
  paint();
  return {stop};
};
