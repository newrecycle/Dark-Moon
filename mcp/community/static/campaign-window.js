"use strict";
(function(root) {
  function stamp(value) {
    if (typeof value !== "string" || !/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)$/.test(value)) throw new Error("Use timezone-aware ISO timestamps");
    const [y,m,d] = value.slice(0,10).split("-").map(Number), civil = new Date(Date.UTC(y,m-1,d));
    if(civil.getUTCFullYear()!==y || civil.getUTCMonth()!==m-1 || civil.getUTCDate()!==d || !Number.isFinite(Date.parse(value))) throw new Error("Invalid assessment window");
    return Date.parse(value);
  }
  function read(hash) {
    const q = new URLSearchParams(String(hash).split("?")[1] || ""), result = {};
    for(const key of ["from","to"]) if(q.has(key)) {
      if(q.getAll(key).length!==1 || !q.get(key)) throw new Error("Use one nonblank window bound");
      result[key]=new Date(stamp(q.get(key))).toISOString();
    }
    if(result.from && result.to && stamp(result.from)>=stamp(result.to)) throw new Error("From must precede Before");
    return result;
  }
  function ids(campaigns, bounds) {
    const lower=bounds.from?stamp(bounds.from):-Infinity, upper=bounds.to?stamp(bounds.to):Infinity;
    if(lower>=upper) throw new Error("From must precede Before");
    return new Set(campaigns.filter(c=>{
      try { const t=stamp(c.date); return t>=lower && t<upper; } catch {return false;}
    }).map(c=>c.id));
  }
  function cohort(snapshot,bounds) {
    if(!bounds.from && !bounds.to)return snapshot;
    const selected=ids(snapshot.campaigns,bounds), campaigns=snapshot.campaigns.filter(c=>selected.has(c.id)), findings=snapshot.findings.filter(f=>selected.has(f.campaign_id));
    const targets=new Set([...campaigns,...findings].map(x=>x.target_id)), projects=new Set([...campaigns,...findings].map(x=>x.project_id));
    return {...snapshot,campaigns,findings,targets:snapshot.targets.filter(t=>targets.has(t.id)),projects:snapshot.projects.filter(p=>projects.has(p.id)),remediations:snapshot.remediations.filter(r=>selected.has(r.campaign_id))};
  }
  function url(page,bounds,extra={}) { const q=new URLSearchParams({...bounds,...extra}); return `#${page}${q.size?'?'+q:''}`; }
  const api={read,ids,cohort,url,stamp};
  if(typeof module!=="undefined")module.exports=api;else root.CampaignWindow=api;
})(globalThis);
