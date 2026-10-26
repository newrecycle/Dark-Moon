#!/usr/bin/env node
/*
 * TEST DOUBLE of the `darkmoon-ci` CLI (the shipped TypeScript @darkmoon/client).
 * It is NOT product code and is NOT bundled in the plugin. Its sole job is to
 * emit the FROZEN contract JSON (camelCase) derived from the SAME raw fixtures
 * the TypeScript conformance suite consumes, so the Kotlin CliDarkmoonClient can
 * be exercised over a real subprocess boundary. When the real darkmoon-ci ships,
 * the plugin points at it instead — identical contract, identical wire shapes.
 *
 * The raw->contract normalization and redaction below mirror the documented
 * contract semantics; the authoritative implementation lives in the TS client.
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const FIX = process.env.DARKMOON_FIXTURES;
if (!FIX) { process.stderr.write("DARKMOON_FIXTURES not set\n"); process.exit(2); }

const argv = process.argv.slice(2);
const flags = {};
const pos = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith("--")) {
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith("--")) { flags[key] = next; i++; }
    else flags[key] = true;
  } else pos.push(a);
}
const mode = flags.mode || "auto";
const edition = mode === "pro" ? "pro" : "oss";
const dir = join(FIX, edition === "pro" ? "pro" : "oss");

function readJson(p) { return JSON.parse(readFileSync(p, "utf8")); }
function out(obj) { process.stdout.write(JSON.stringify(obj)); }

// ---- redaction (used when NOT --full) --------------------------------------
function redactText(s) {
  if (s == null) return s;
  return String(s)
    // JWTs / long base64 blobs
    .replace(/eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.?[A-Za-z0-9_\-]*/g, "<REDACTED_TOKEN>")
    .replace(/[A-Za-z0-9+/]{40,}={0,2}/g, "<REDACTED_BLOB>")
    // IPv4[:port]
    .replace(/\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b/g, "<REDACTED_HOST>")
    // md5/sha-like hex
    .replace(/\b[a-f0-9]{32,64}\b/g, "<REDACTED_HASH>");
}

// ---- normalizers (raw snake_case -> contract camelCase) ---------------------
function normSeveritySummary(stats) {
  stats = stats || {};
  return {
    critical: stats.critical || 0,
    high: stats.high || 0,
    medium: stats.medium || 0,
    low: stats.low || 0,
    info: stats.info || 0,
    total: stats.total_findings != null ? stats.total_findings :
      (stats.critical||0)+(stats.high||0)+(stats.medium||0)+(stats.low||0)+(stats.info||0),
  };
}
function targetFromReportPath(p) {
  if (!p) return null;
  const m = String(p).match(/pentest_report_([^_]+)_/);
  return m ? m[1] : null;
}
function normCampaign(c) {
  return {
    id: c.id,
    projectId: c.project_id ?? null,
    targetId: c.target_id ?? null,
    sessionId: c.session_id ?? null,
    target: c.target ?? targetFromReportPath(c.report_path),
    status: c.status || "unknown",
    overallRisk: c.overall_risk || "none",
    createdAt: c.date ?? null,
    durationSeconds: c.duration_seconds ?? null,
    reportPath: c.report_path ?? null,
    isSubagent: !!c.is_subagent,
    severity: normSeveritySummary(c.stats),
    executiveSummary: c.executive_summary ?? null,
    edition,
  };
}
function normEvidence(ev, full) {
  if (!ev) return null;
  const t = (s) => full ? (s ?? null) : (s == null ? null : redactText(s));
  const arr = (a) => (a || []).map((x) => full ? x : redactText(x));
  return {
    commands: arr(ev.commands),
    payloads: arr(ev.payloads),
    rawRequest: t(ev.raw_request),
    rawResponse: t(ev.raw_response),
    extractedData: t(ev.extracted_data),
    logs: arr(ev.logs),
    explanation: t(ev.explanation),
    redacted: !full,
  };
}
function normFinding(f, includeEvidence, full) {
  return {
    id: f.id || f.node_id,
    campaignId: f.campaign_id ?? null,
    projectId: f.project_id ?? null,
    targetId: f.target_id ?? null,
    title: f.title ?? null,
    severity: f.severity,
    status: f.status,
    category: f.category ?? null,
    cve: f.cve ?? null,
    cvssScore: f.cvss_score ?? null,
    cvssVector: f.cvss_vector ?? null,
    mitreAttackId: f.mitre_attack_id ?? null,
    mitreAttackName: f.mitre_attack_name ?? null,
    endpoint: f.endpoint ?? null,
    description: f.description ?? null,
    remediation: f.remediation ?? null,
    discoveredByAgent: f.discovered_by_agent ?? null,
    discoveredAt: f.discovered_at ?? null,
    evidence: includeEvidence ? normEvidence(f.evidence, full) : null,
    edition,
  };
}

// fixture discovery
const CAMPS = {
  oss: [
    { id: "camp_20260924_70602bf9", camp: "camp_20260924_70602bf9.campaign.json",
      vulns: "camp_20260924_70602bf9.vulns.json", report: "report_70602bf9.md", session: "70602bf9" },
    { id: "camp_20260728_9018be77", camp: "camp_20260728_9018be77.campaign.json",
      vulns: "camp_20260728_9018be77.vulns.json", report: null, session: "9018be77" },
  ],
  pro: [
    { id: "camp_pro", camp: "camp_pro.json", vulns: null },
    { id: "alive", camp: "alive.json", vulns: null },
    { id: "dead", camp: "dead.json", vulns: null },
    { id: "slow", camp: "slow.json", vulns: null },
    { id: "sub", camp: "sub.json", vulns: null },
  ],
};
function campEntry(id) { return (CAMPS[edition] || []).find((c) => c.id === id); }
function loadCampaign(id) {
  const e = campEntry(id);
  if (!e) return null;
  return normCampaign(readJson(join(dir, e.camp)));
}

const cmd = pos.join(" ");

try {
  if (pos[0] === "detect") {
    const pro = edition === "pro";
    out({
      edition,
      mode: edition,
      version: pro ? "1.3.1" : "community-1.3.1",
      available: true,
      features: {
        restApi: pro, streaming: pro, auth: pro,
        remediation: pro, dashboard: pro, scheduler: pro,
      },
      detectedBy: pro ? "root-probe" : "system-info",
      warnings: pro ? ["must_change_password: the Pro admin still has the default password"] : [],
    });
  } else if (pos[0] === "campaigns" && pos[1] === "list") {
    let list = (CAMPS[edition] || []).map((e) => normCampaign(readJson(join(dir, e.camp))));
    if (flags.status) list = list.filter((c) => c.status === flags.status);
    if (flags["target-id"]) list = list.filter((c) => c.targetId === flags["target-id"]);
    out(list);
  } else if (pos[0] === "campaign" && (pos[1] === "get" || pos[1] === "status")) {
    const c = loadCampaign(pos[2]);
    if (!c) { process.stderr.write(`unknown campaign ${pos[2]}\n`); process.exit(1); }
    out(c);
  } else if (pos[0] === "summary") {
    const c = loadCampaign(pos[1]);
    if (!c) { process.stderr.write(`unknown campaign ${pos[1]}\n`); process.exit(1); }
    out(c.severity);
  } else if (pos[0] === "findings" && pos[1] === "list") {
    const includeEv = !!flags["include-evidence"];
    const full = !!flags.full;
    let all = [];
    const ids = flags.campaign ? [flags.campaign] : (CAMPS[edition] || []).map((e) => e.id);
    for (const id of ids) {
      const e = campEntry(id);
      if (!e || !e.vulns) continue;
      const raw = readJson(join(dir, e.vulns));
      all = all.concat(raw.map((f) => normFinding(f, includeEv, full)));
    }
    if (flags.severity) all = all.filter((f) => f.severity === flags.severity);
    if (flags.status) all = all.filter((f) => f.status === flags.status);
    if (flags.category) all = all.filter((f) => f.category === flags.category);
    out(all);
  } else if (pos[0] === "finding" && pos[1] === "get") {
    const includeEv = !!flags["include-evidence"];
    const full = !!flags.full;
    const wantId = pos[2];
    for (const e of (CAMPS[edition] || [])) {
      if (!e.vulns) continue;
      const raw = readJson(join(dir, e.vulns));
      const hit = raw.find((f) => (f.id || f.node_id) === wantId);
      if (hit) { out(normFinding(hit, includeEv, full)); process.exit(0); }
    }
    process.stderr.write(`unknown finding ${wantId}\n`); process.exit(1);
  } else if (pos[0] === "report") {
    const e = campEntry(pos[1]);
    const full = !!flags.full;
    if (!e || !e.report || !existsSync(join(dir, e.report))) {
      out({ campaignId: pos[1], format: "markdown", content: "", ready: false, redacted: !full });
    } else {
      let content = readFileSync(join(dir, e.report), "utf8");
      if (!full) content = redactText(content);
      out({ campaignId: pos[1], format: "markdown", content, ready: true, redacted: !full });
    }
  } else if (pos[0] === "launch") {
    const now = Date.now();
    const pro = edition === "pro";
    out({
      correlation: {
        edition,
        runId: pro ? "run_stub_" + now : null,
        campaignId: null,
        nonce: pro ? null : "nonce_" + now,
        preCampaignIds: (CAMPS[edition] || []).map((e) => e.id),
        startedAtMs: now,
      },
      campaignId: null,
      runId: pro ? "run_stub_" + now : null,
    });
  } else if (pos[0] === "stream") {
    process.stdout.write(JSON.stringify({ type: "run_started", runId: pos[1], message: "started" }) + "\n");
    process.stdout.write(JSON.stringify({ type: "phase", message: "recon", terminal: false }) + "\n");
    process.stdout.write(JSON.stringify({ type: "run_completed", campaignId: pos[1], terminal: true }) + "\n");
  } else {
    process.stderr.write("unknown command: " + cmd + "\n");
    process.exit(2);
  }
} catch (err) {
  process.stderr.write("stub error: " + (err && err.message) + "\n");
  process.exit(3);
}
