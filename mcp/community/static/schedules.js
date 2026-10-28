"use strict";
window.ScheduleUI = (() => {
  let editing = null, previewVersion = 0;
  const form = () => $("#launch-form");
  function localValue(timestamp, timezone) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {timeZone:timezone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(new Date(timestamp)).map(p=>[p.type,p.value]));
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
  }
  function configure(record = null) {
    editing = record; previewVersion++;
    const f=form(), timezone=record?.rule?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    $("#schedule-timezones").innerHTML=[...new Set(["UTC",timezone,...(Intl.supportedValuesOf?.("timeZone")||[])])].map(z=>`<option value="${esc(z)}"></option>`).join("");
    if (record) {
      for (const [key,value] of Object.entries(record.spec)) {
        const control=f.elements[key]; if (!control) continue;
        if (control.type==="checkbox") control.checked=Boolean(value);
        else if (control.tagName==="SELECT") {
          const values=control.multiple ? String(value).split(",").filter(Boolean) : [String(value)];
          for (const v of values) if (![...control.options].some(o=>o.value===v)) control.add(new Option(v,v));
          for (const option of control.options) option.selected=values.includes(option.value);
        } else control.value=Array.isArray(value)?value.join(","):value;
      }
    }
    f.elements.schedule_name.value=record?.display_name || record?.spec.name || "";
    f.elements.schedule_kind.value=record?.rule?.kind || (record?.one_shot?"once":"interval");
    f.elements.schedule_timezone.value=timezone;
    f.elements.schedule_every.value=record?.rule?.every || 1;
    f.elements.schedule_fold.value=record?.rule?.fold || 0;
    f.elements.schedule_enabled.checked=record?record.enabled:true;
    if (record) f.elements.first_run.value=record.rule?.start_local || localValue(record.next_run,timezone);
    f.elements.hours.value=record?record.interval_seconds/3600:24;
    $("#schedule-preview").textContent="";
    changed();
  }
  function changed() {
    previewVersion++;
    const f=form(), kind=f.elements.schedule_kind.value;
    for (const control of $("#schedule-fields").querySelectorAll("input,select,button")) control.disabled=!scheduleMode;
    $("#schedule-hours").hidden=kind!=="interval";
    f.elements.hours.disabled=!scheduleMode || kind!=="interval";
    $("#schedule-every").hidden=!["daily","weekly","monthly"].includes(kind);
    f.elements.schedule_every.disabled=!scheduleMode || !["daily","weekly","monthly"].includes(kind);
    for (const key of ["first_run","schedule_timezone"]) f.elements[key].required=scheduleMode;
    $("#schedule-preview").textContent="";
  }
  function payload() {
    const f=form(), spec=window.launchValues(f), kind=f.elements.schedule_kind.value;
    spec.remediate=f.elements.remediate.checked;
    const rule={kind,timezone:f.elements.schedule_timezone.value.trim(),start_local:f.elements.first_run.value,fold:Number(f.elements.schedule_fold.value),every:1};
    if (kind==="interval") rule.seconds=Math.round(Number(f.elements.hours.value)*3600);
    if (["daily","weekly","monthly"].includes(kind)) rule.every=Number(f.elements.schedule_every.value);
    return {spec,rule,display_name:f.elements.schedule_name.value || spec.name,enabled:f.elements.schedule_enabled.checked};
  }
  async function preview() {
    const version=++previewVersion;
    $("#schedule-preview").textContent="Calculating occurrences…";
    try {
      const result=await api("/api/v1/scheduler/preview",{method:"POST",body:JSON.stringify(payload())});
      if (version!==previewVersion || !$("#launch-dialog").open || !token) return;
      $("#schedule-preview").innerHTML=`<p>${esc(result.timezone)} · DST gaps and missing month dates are skipped.</p><ol>${result.occurrences.map(o=>`<li><strong>${esc(o.local)}</strong>${o.overdue?' · overdue; runs once when enabled':""}<small>UTC ${esc(o.utc)}</small></li>`).join("")}</ol>`;
    } catch(error) {if(version===previewVersion && token) $("#schedule-preview").textContent=error.message;}
  }
  function label(item) {
    const r=item.rule;
    if (!r) return item.one_shot?"One time":`Every ${+(item.interval_seconds/3600).toFixed(2)} hours`;
    if (r.kind==="once") return `One time · ${r.timezone}`;
    if (r.kind==="interval") return `Every ${+(r.seconds/3600).toFixed(2)} elapsed hours · ${r.timezone}`;
    return `Every ${r.every} ${ {daily:"day(s)",weekly:"week(s)",monthly:"month(s)"}[r.kind]} · ${r.start_local.slice(11)} · ${r.timezone}`;
  }
  function table(items) {
    if (!items.length) return empty("No scheduled assessments","Create a one-time, elapsed-interval or calendar assessment.");
    return `<div class="table-scroll"><table><thead><tr><th>SCHEDULE / ASSESSMENT</th><th>RULE</th><th>NEXT RUN</th><th>LAST RESULT</th><th>ACTIONS</th></tr></thead><tbody>${items.map(s=>`<tr><td>${esc(s.display_name||s.spec.name)}<small>${esc(s.spec.name)} · ${esc(s.spec.target)}</small></td><td>${esc(label(s))}</td><td>${s.enabled?esc(date(s.next_run)):"Paused / consumed"}<small>${s.enabled?"Enabled":"Disabled"} · version ${s.version||1}</small></td><td>${esc(s.last_disposition||"Not run")}<small>${esc(s.last_error||"")}</small></td><td><div class="schedule-actions"><button class="secondary" data-edit-schedule="${esc(s.id)}">Edit</button><button class="secondary" data-duplicate-schedule="${esc(s.id)}">Duplicate paused</button><button class="secondary" data-schedule-history="${esc(s.id)}">History</button><button class="secondary" data-toggle-schedule="${esc(s.id)}">${s.enabled?"Pause":s.one_shot&&s.last_tick?"Re-arm once":"Resume"}</button><button class="secondary" data-delete-schedule="${esc(s.id)}">Delete</button></div></td></tr>`).join("")}</tbody></table></div>`;
  }
  $("#schedule-preview-button").addEventListener("click",preview);
  $("#launch-form").addEventListener("input",e=>{if(e.target.closest("#schedule-fields"))changed();});
  $("#launch-form").addEventListener("change",e=>{if(e.target.closest("#schedule-fields"))changed();});
  return {configure,changed,payload,table,editing:()=>editing};
})();
