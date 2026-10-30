"use strict";
(function (root) {
  const valid = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,200}$/.test(value);
  const resources = ["campaign", "vulnerability", "project", "report", "infra", "pull-request"];
  const pages = {login:"overview", "change-password":"settings", "new-campaign":"campaigns", scheduler:"schedules", history:"campaigns", projects:"projects"};
  function read(hash) {
    const parts = String(hash).replace(/^#\/?/, "").split("?");
    if (parts.length > 2) return null;
    const [path, query = ""] = parts, [kind, id, extra] = path.split("/");
    const params = new URLSearchParams(query);
    if (Object.hasOwn(pages, kind)) return id === undefined && !params.size ? {kind, page:pages[kind]} : null;
    if (!resources.includes(kind) || !valid(id) || extra !== undefined) return null;
    if (kind !== "vulnerability") return !params.size ? {kind, id} : null;
    if (!params.size) return {kind, id};
    const cid = params.get("campaign_id");
    return params.size === 1 && valid(cid) ? {kind, id, campaignId:cid} : null;
  }
  function link(kind, id, campaignId) {
    if (!valid(id) || !resources.includes(kind) || campaignId !== undefined && !valid(campaignId)) throw new Error("Invalid resource identity");
    return `#${kind}/${id}${kind === "vulnerability" && campaignId ? `?campaign_id=${campaignId}` : ""}`;
  }
  function fromPath(path, search = "") {
    const value = read(path.replace(/^\//, "") + search);
    return value ? value.id ? link(value.kind, value.id, value.campaignId) : `#${value.kind}` : null;
  }
  const api = {read, link, fromPath};
  if (typeof module !== "undefined") module.exports = api;
  else root.ResourceRoutes = api;
})(globalThis);
