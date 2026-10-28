"use strict";
// Shared pure URL/filter/sort/page logic, also exercised directly in Node.
const FindingQuery = (() => {
  const filters = ["severity", "status", "category", "campaign_id", "target_id"];
  const sorts = ["severity_desc", "severity_asc", "cvss_desc", "cvss_asc", "title_asc", "title_desc", "status_asc", "status_desc", "campaign_asc", "campaign_desc", "target_asc", "target_desc"];
  const severity = {critical:5,high:4,medium:3,low:2,info:1};
  const positive = value => /^\d+$/.test(value || "") && Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : 1;
  function read(hash) {
    const q = new URLSearchParams(hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "");
    return {q:(q.get("q") || "").slice(0,500), ...Object.fromEntries(filters.map(k => [k,q.get(k)||""])),
      sort:sorts.includes(q.get("sort"))?q.get("sort"):"severity_desc", page:positive(q.get("page")),
      size:[5,10,25,50,100].includes(Number(q.get("size")))?Number(q.get("size")):50};
  }
  function hash(state) {
    const q = new URLSearchParams();
    for (const k of ["q",...filters,"sort","size","page"]) {
      if (state[k] && !(k==="sort" && state[k]==="severity_desc") && !(k==="size" && state[k]===50) && !(k==="page" && state[k]===1)) q.set(k,state[k]);
    }
    return "#findings"+(q.size?"?"+q.toString():"");
  }
  function page(items,state) {
    const text = state.q.trim().toLowerCase();
    const all = items.filter(f => filters.every(k => !state[k] || String(f[k] ?? "")===state[k]) &&
      (!text || ["id","title","endpoint","category","campaign_id","target_id"].map(k=>f[k]||"").join(" ").toLowerCase().includes(text)));
    const [field,direction] = state.sort.split("_");
    const cmp=(a,b)=>(a>b)-(a<b);
    const key=f=>field==="severity" ? severity[String(f.severity).toLowerCase()]||0
      :field==="cvss" ? f.cvss_score!==null && f.cvss_score!==undefined && f.cvss_score!=="" && Number.isFinite(Number(f.cvss_score))?Number(f.cvss_score):null
      :String(f[({campaign:"campaign_id",target:"target_id"})[field]||field]||"").toLowerCase();
    all.sort((a,b)=>{
      const x=key(a),y=key(b);
      const order=x===null||y===null ? Number(x===null)-Number(y===null) : cmp(x,y)*(direction==="desc"?-1:1);
      return order || cmp(String(a.campaign_id||""),String(b.campaign_id||"")) || cmp(String(a.id||""),String(b.id||""));
    });
    const pages=Math.max(1,Math.ceil(all.length/state.size)), current=Math.min(state.page,pages), offset=(current-1)*state.size;
    return {items:all.slice(offset,offset+state.size),total:all.length,pages,page:current,offset};
  }
  return {read,hash,page,filters,sorts};
})();
if (typeof module !== "undefined") module.exports = FindingQuery;
