"use strict";
(function (root) {
  const valid = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,200}$/.test(value);
  function read(hash) {
    const [path, query = ""] = String(hash).replace(/^#/, "").split("?");
    const [kind, id, extra] = path.split("/");
    if (!["campaign", "vulnerability"].includes(kind) || !valid(id) || extra !== undefined) return null;
    const params = new URLSearchParams(query);
    if (kind === "campaign") return params.size === 0 ? {kind, id} : null;
    const cid = params.get("campaign_id");
    return params.size === 1 && valid(cid) ? {kind, id, campaignId:cid} : null;
  }
  function link(kind, id, campaignId) {
    if (!valid(id) || !["campaign", "vulnerability"].includes(kind) || kind === "vulnerability" && !valid(campaignId)) throw new Error("Invalid resource identity");
    return `#${kind}/${id}${kind === "vulnerability" ? `?campaign_id=${campaignId}` : ""}`;
  }
  const api = {read, link};
  if (typeof module !== "undefined") module.exports = api;
  else root.ResourceRoutes = api;
})(globalThis);
