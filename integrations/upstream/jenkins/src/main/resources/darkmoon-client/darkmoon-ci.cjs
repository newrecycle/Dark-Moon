#!/usr/bin/env node
"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// cli/darkmoon-ci.ts
var import_node_util = require("util");
var import_node_fs3 = require("fs");

// src/backends/pro-http.ts
var import_node_crypto = require("crypto");

// src/backends/backend.ts
function refToId(ref) {
  if (typeof ref === "string") return ref;
  return ref.campaignId ?? null;
}

// src/errors.ts
var DarkmoonError = class extends Error {
  constructor(code, message, details) {
    super(message);
    this.name = "DarkmoonError";
    this.code = code;
    this.details = details;
    Object.setPrototypeOf(this, new.target.prototype);
  }
};
var DarkmoonNotAvailable = class extends DarkmoonError {
  constructor(message = "Darkmoon backend is not reachable (neither Pro API nor OSS CLI).", details) {
    super("DARKMOON_NOT_AVAILABLE", message, details);
    this.name = "DarkmoonNotAvailable";
  }
};
var AuthError = class extends DarkmoonError {
  constructor(message = "Authentication failed.", details) {
    super("AUTH_FAILED", message, details);
    this.name = "AuthError";
  }
};
var UnsupportedVersion = class extends DarkmoonError {
  constructor(message, details) {
    super("UNSUPPORTED_VERSION", message, details);
    this.name = "UnsupportedVersion";
  }
};
var ReportNotReady = class extends DarkmoonError {
  constructor(message = "The campaign report is not ready yet.", details) {
    super("REPORT_NOT_READY", message, details);
    this.name = "ReportNotReady";
  }
};
var CampaignNotFound = class extends DarkmoonError {
  constructor(message = "Campaign not found.", details) {
    super("CAMPAIGN_NOT_FOUND", message, details);
    this.name = "CampaignNotFound";
  }
};
var FindingNotFound = class extends DarkmoonError {
  constructor(message = "Finding not found.", details) {
    super("FINDING_NOT_FOUND", message, details);
    this.name = "FindingNotFound";
  }
};
var CorrelationFailed = class extends DarkmoonError {
  constructor(message = "Could not correlate the launched run to a campaign.", details) {
    super("CORRELATION_FAILED", message, details);
    this.name = "CorrelationFailed";
  }
};
var StuckCampaignError = class extends DarkmoonError {
  constructor(message = "Campaign is stuck and did not reach a terminal state within the timeout.", details) {
    super("STUCK_CAMPAIGN", message, details);
    this.name = "StuckCampaignError";
  }
};
var NetworkError = class extends DarkmoonError {
  constructor(message = "Network error talking to the Darkmoon API.", details) {
    super("NETWORK", message, details);
    this.name = "NetworkError";
  }
};
var SchemaInvalid = class extends DarkmoonError {
  constructor(message = "Backend returned data that does not match the expected schema.", details) {
    super("SCHEMA_INVALID", message, details);
    this.name = "SchemaInvalid";
  }
};
var InsecureDefaultError = class extends DarkmoonError {
  constructor(message = "Backend is running with an insecure default (must_change_password / default secret).", details) {
    super("INSECURE_DEFAULT", message, details);
    this.name = "InsecureDefaultError";
  }
};
var NotSupported = class extends DarkmoonError {
  constructor(message, details) {
    super("NOT_SUPPORTED", message, details);
    this.name = "NotSupported";
  }
};

// src/util/http.ts
async function httpRequest(url, opts = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 15e3);
  const headers = { Accept: "application/json", ...opts.headers };
  let body;
  if (opts.body !== void 0) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  let res;
  let text;
  try {
    res = await fetch(url, { method: opts.method ?? "GET", headers, body, signal: controller.signal, redirect: "manual" });
    text = await res.text();
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new NetworkError(`Request timed out after ${opts.timeoutMs ?? 15e3}ms.`, { url: safeUrl(url) });
    }
    throw new NetworkError(`Could not reach ${safeUrl(url)}: ${err?.code ?? err?.name ?? "connection failed"}.`, { url: safeUrl(url) });
  } finally {
    clearTimeout(timeout);
  }
  let data = void 0;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (res.ok) throw new SchemaInvalid("API returned malformed JSON.", { url: safeUrl(url) });
      data = void 0;
    }
  }
  if (res.status === 401 || res.status === 403) {
    if (!opts.allowStatuses?.includes(res.status)) {
      throw new AuthError(`Unauthorized (HTTP ${res.status}).`, { url: safeUrl(url) });
    }
  }
  if (!res.ok && !opts.allowStatuses?.includes(res.status)) {
    throw new DarkmoonError("NETWORK", `HTTP ${res.status} from ${safeUrl(url)}.`, { status: res.status });
  }
  return { status: res.status, ok: res.ok, data, text, headers: res.headers };
}
function safeUrl(url) {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}${u.pathname}`;
  } catch {
    return url.split("?")[0] ?? url;
  }
}

// src/util/sse.ts
async function* readSse(url, opts = {}) {
  const headers = { Accept: "text/event-stream" };
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeoutMs = opts.timeoutMs ?? 15e3;
  let timer;
  const arm = () => {
    clearTimeout(timer);
    timer = setTimeout(abort, timeoutMs);
  };
  let reader;
  if (opts.signal?.aborted) return;
  opts.signal?.addEventListener("abort", abort, { once: true });
  try {
    arm();
    const res = await fetch(url, { headers, signal: controller.signal, redirect: "manual" });
    if (res.status === 401 || res.status === 403) throw new AuthError(`SSE unauthorized (HTTP ${res.status}).`);
    if (!res.ok || !res.body) throw new NetworkError(`SSE stream returned HTTP ${res.status}.`, { status: res.status });
    if (!/^text\/event-stream(?:;|$)/i.test(res.headers.get("content-type") ?? "")) throw new SchemaInvalid("SSE response has an invalid content type.");
    reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let data = [];
    let frameSize = 0;
    for (; ; ) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim() || data.length) throw new SchemaInvalid("SSE ended with an incomplete frame.");
        return;
      }
      arm();
      buffer += decoder.decode(value, { stream: true });
      for (; ; ) {
        const match = /\r\n|\r|\n/.exec(buffer);
        if (!match || match[0] === "\r" && match.index === buffer.length - 1) break;
        const line = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        frameSize += line.length;
        if (frameSize > 1024 * 1024) throw new SchemaInvalid("SSE frame exceeds the size limit.");
        if (!line) {
          if (data.length) {
            let payload;
            try {
              payload = JSON.parse(data.join("\n"));
            } catch {
              throw new SchemaInvalid("SSE returned malformed JSON.");
            }
            data = [];
            yield payload;
          }
          frameSize = 0;
        } else if (line.startsWith("data:")) {
          data.push(line.slice(5).replace(/^ /, ""));
        }
      }
      if (buffer.length + frameSize > 1024 * 1024) throw new SchemaInvalid("SSE frame exceeds the size limit.");
    }
  } catch (err) {
    if (opts.signal?.aborted) return;
    if (err instanceof DarkmoonError) throw err;
    throw new NetworkError("SSE connection failed or timed out; completion is unverified.");
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", abort);
    controller.abort();
    await reader?.cancel().catch(() => void 0);
    reader?.releaseLock();
  }
}

// src/redact.ts
var SECRET_PATTERNS = [
  // JWT (three base64url segments)
  { re: /\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b/g, label: "JWT" },
  // Common LLM / provider keys
  { re: /\bsk-(?:ant-|proj-|or-|live-)?[A-Za-z0-9_-]{16,}\b/g, label: "API_KEY" },
  { re: /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, label: "SLACK_TOKEN" },
  { re: /\bghp_[A-Za-z0-9]{20,}\b/g, label: "GITHUB_PAT" },
  { re: /\bglpat-[A-Za-z0-9_-]{16,}\b/g, label: "GITLAB_PAT" },
  { re: /\bAKIA[0-9A-Z]{16}\b/g, label: "AWS_KEY" },
  { re: /\bAIza[0-9A-Za-z_-]{30,}\b/g, label: "GOOGLE_KEY" },
  // Cryptolens-style license keys (grouped alnum blocks)
  { re: /\b[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}\b/g, label: "LICENSE_KEY" },
  // Bearer headers
  { re: /\bBearer\s+[A-Za-z0-9._-]{12,}/gi, label: "BEARER" },
  // Authorization / password / token key=value pairs in text
  { re: /\b(authorization|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*["']?[^\s"',}]{6,}/gi, label: "CREDENTIAL" }
];
var MASK = "\xABREDACTED:$LABEL\xBB";
function scrubSecrets(input) {
  if (!input) return input;
  let out2 = input;
  for (const { re, label } of SECRET_PATTERNS) {
    out2 = out2.replace(re, (m) => {
      const eq = m.match(/^([A-Za-z_-]+)\s*[:=]/);
      const prefix = eq ? `${eq[1]}=` : "";
      return prefix + MASK.replace("$LABEL", label);
    });
  }
  return out2;
}
function redactReport(markdown) {
  if (!markdown) return markdown;
  const withoutFences = markdown.replace(/```[^\n]*\n[\s\S]*?```/g, (block) => {
    const firstLine = block.slice(0, block.indexOf("\n") + 1);
    return `${firstLine}\xABevidence redacted \u2014 use getReport({ full: true, private: true }) for the full report\xBB
\`\`\``;
  });
  return scrubSecrets(withoutFences);
}

// src/util/logger.ts
var ORDER = { silent: 0, error: 1, warn: 2, info: 3, debug: 4 };
var Logger = class {
  constructor(level = "warn", sink = (l) => process.stderr.write(l + "\n")) {
    this.level = level;
    this.sink = sink;
  }
  setLevel(level) {
    this.level = level;
  }
  emit(level, msg) {
    if (ORDER[this.level] >= ORDER[level]) {
      this.sink(`[darkmoon:${level}] ${scrubSecrets(msg)}`);
    }
  }
  error(msg) {
    this.emit("error", msg);
  }
  warn(msg) {
    this.emit("warn", msg);
  }
  info(msg) {
    this.emit("info", msg);
  }
  debug(msg) {
    this.emit("debug", msg);
  }
};

// src/contract.ts
var CONTRACT_VERSION = "1.0.0";
var SEVERITIES = ["critical", "high", "medium", "low", "info"];

// src/redact-evidence.ts
function redactEvidence(ev) {
  return {
    commands: ev.commands.map(scrubSecrets),
    payloads: ev.payloads.map(scrubSecrets),
    rawRequest: ev.rawRequest ? "\xABredacted \u2014 opt in with { full: true, private: true }\xBB" : null,
    rawResponse: ev.rawResponse ? "\xABredacted \u2014 opt in with { full: true, private: true }\xBB" : null,
    extractedData: ev.extractedData ? "\xABredacted\xBB" : null,
    logs: ev.logs.map(scrubSecrets),
    explanation: ev.explanation ? scrubSecrets(ev.explanation) : null,
    redacted: true
  };
}

// src/normalize.ts
function normalizeSeverity(input) {
  const s = String(input ?? "").trim().toLowerCase();
  switch (s) {
    case "critical":
    case "crit":
      return "critical";
    case "high":
    case "severe":
      return "high";
    case "medium":
    case "moderate":
    case "med":
      return "medium";
    case "low":
    case "minor":
      return "low";
    case "info":
    case "informational":
    case "information":
    case "none":
    case "":
      return "info";
    default:
      return SEVERITIES.includes(s) ? s : "info";
  }
}
function normalizeRisk(input) {
  const s = String(input ?? "").trim().toLowerCase();
  if (s === "none" || s === "") return "none";
  return normalizeSeverity(s);
}
function normalizeFindingStatus(input) {
  const s = String(input ?? "").trim().toLowerCase();
  if (s.includes("remediat") || s.includes("fixed")) return "remediated";
  if (s.includes("exploit")) return "exploited";
  if (s.includes("confirm") && !s.includes("unconfirm")) return "confirmed";
  return "unconfirmed";
}
function normalizeCampaignStatus(input) {
  const s = String(input ?? "").trim().toLowerCase();
  if (["completed", "complete", "done", "finished", "succeeded", "success"].includes(s)) return "completed";
  if (["running", "in_progress", "active"].includes(s)) return "running";
  if (["queued", "pending", "scheduled"].includes(s)) return "queued";
  if (["stopped", "cancelled", "canceled", "killed", "aborted"].includes(s)) return "stopped";
  if (["failed", "failure", "error", "crashed", "timed_out", "timeout", "interrupted"].includes(s)) return "failed";
  return "unknown";
}
function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function str(v) {
  if (v === null || v === void 0) return null;
  const s = String(v);
  return s.length ? s : null;
}
function severitySummaryFromStats(stats) {
  const s = stats ?? {};
  const critical = num(s.critical);
  const high = num(s.high);
  const medium = num(s.medium);
  const low = num(s.low);
  const info = num(s.info);
  const total = s.total_findings !== void 0 ? num(s.total_findings) : critical + high + medium + low + info;
  return { critical, high, medium, low, info, total };
}
function severitySummaryFromFindings(findings) {
  const sum = { critical: 0, high: 0, medium: 0, low: 0, info: 0, total: 0 };
  for (const f of findings) {
    sum[f.severity] += 1;
    sum.total += 1;
  }
  return sum;
}
function targetFromCampaign(raw) {
  const direct = str(raw.target) ?? str(raw.host) ?? str(raw.target_stack?.host);
  if (direct) return direct;
  const rp = str(raw.report_path);
  if (rp) {
    const m = rp.match(/pentest_report_(.+)_\d{8}-\d{4,6}\.md$/);
    if (m && m[1]) return m[1];
  }
  return null;
}
function normalizeCampaign(raw, edition) {
  return {
    id: String(raw.id ?? ""),
    projectId: str(raw.project_id),
    targetId: str(raw.target_id),
    sessionId: str(raw.session_id),
    target: targetFromCampaign(raw),
    status: normalizeCampaignStatus(raw.status),
    overallRisk: normalizeRisk(raw.overall_risk),
    createdAt: str(raw.date) ?? str(raw.created_at),
    durationSeconds: raw.duration_seconds !== void 0 ? num(raw.duration_seconds) : null,
    reportPath: str(raw.report_path),
    isSubagent: Boolean(raw.is_subagent),
    severity: severitySummaryFromStats(raw.stats),
    executiveSummary: str(raw.executive_summary),
    edition,
    raw
  };
}
function evidenceFrom(raw, edition, includeEvidence, full) {
  if (!includeEvidence || !raw) return null;
  const ev = {
    commands: Array.isArray(raw.commands) ? raw.commands.map(String) : [],
    payloads: Array.isArray(raw.payloads) ? raw.payloads.map(String) : [],
    rawRequest: str(raw.raw_request),
    rawResponse: str(raw.raw_response),
    extractedData: raw.extracted_data == null ? null : String(raw.extracted_data),
    logs: Array.isArray(raw.logs) ? raw.logs.map(String) : [],
    explanation: str(raw.explanation),
    redacted: false
  };
  void edition;
  return full ? ev : redactEvidence(ev);
}
function normalizeFinding(raw, edition, opts) {
  const includeEvidence = opts?.includeEvidence ?? false;
  const full = opts?.full ?? false;
  return {
    id: String(raw.id ?? raw.node_id ?? ""),
    campaignId: str(raw.campaign_id),
    projectId: str(raw.project_id),
    targetId: str(raw.target_id),
    title: str(raw.title),
    severity: normalizeSeverity(raw.severity),
    status: normalizeFindingStatus(raw.status),
    category: str(raw.category),
    cve: str(raw.cve),
    cvssScore: raw.cvss_score == null ? null : num(raw.cvss_score),
    cvssVector: str(raw.cvss_vector),
    mitreAttackId: str(raw.mitre_attack_id),
    mitreAttackName: str(raw.mitre_attack_name),
    endpoint: str(raw.endpoint),
    description: str(raw.description),
    remediation: typeof raw.remediation === "string" ? raw.remediation : str(raw.remediation?.summary),
    discoveredByAgent: str(raw.discovered_by_agent),
    discoveredAt: str(raw.discovered_at),
    evidence: evidenceFrom(raw.evidence, edition, includeEvidence, full),
    edition,
    raw
  };
}
function matchesFindingFilter(f, filter) {
  if (filter.campaignId && f.campaignId !== filter.campaignId) return false;
  if (filter.projectId && f.projectId !== filter.projectId) return false;
  if (filter.targetId && f.targetId !== filter.targetId) return false;
  if (filter.severity && f.severity !== normalizeSeverity(filter.severity)) return false;
  if (filter.status && f.status !== normalizeFindingStatus(filter.status)) return false;
  if (filter.category && f.category !== filter.category) return false;
  return true;
}

// src/schema.ts
var import_zod = require("zod");
var SUPPORTED_API_MAJORS = [1];
var looseObject = import_zod.z.object({}).passthrough();
var StatsSchema = looseObject.extend({
  total_findings: import_zod.z.number().optional(),
  critical: import_zod.z.number().optional(),
  high: import_zod.z.number().optional(),
  medium: import_zod.z.number().optional(),
  low: import_zod.z.number().optional(),
  info: import_zod.z.number().optional()
});
var RawCampaignSchema = looseObject.extend({
  id: import_zod.z.string(),
  project_id: import_zod.z.string().nullable().optional(),
  target_id: import_zod.z.string().nullable().optional(),
  session_id: import_zod.z.string().nullable().optional(),
  is_subagent: import_zod.z.boolean().optional(),
  status: import_zod.z.string().optional(),
  overall_risk: import_zod.z.string().optional(),
  report_path: import_zod.z.string().optional(),
  stats: StatsSchema.optional()
});
var RawEvidenceSchema = looseObject.extend({
  commands: import_zod.z.array(import_zod.z.any()).optional(),
  payloads: import_zod.z.array(import_zod.z.any()).optional(),
  raw_request: import_zod.z.string().nullable().optional(),
  raw_response: import_zod.z.string().nullable().optional(),
  extracted_data: import_zod.z.any().optional(),
  logs: import_zod.z.array(import_zod.z.any()).optional(),
  explanation: import_zod.z.string().nullable().optional()
});
var RawFindingSchema = looseObject.extend({
  id: import_zod.z.string().optional(),
  node_id: import_zod.z.string().optional(),
  title: import_zod.z.string().nullable().optional(),
  severity: import_zod.z.string().nullable().optional(),
  status: import_zod.z.string().nullable().optional(),
  category: import_zod.z.string().nullable().optional(),
  cve: import_zod.z.string().nullable().optional(),
  campaign_id: import_zod.z.string().nullable().optional(),
  evidence: RawEvidenceSchema.nullable().optional()
});
var RawFindingArraySchema = import_zod.z.array(RawFindingSchema);
var ProRootSchema = looseObject.extend({
  service: import_zod.z.string().optional(),
  version: import_zod.z.string().optional(),
  status: import_zod.z.string().optional()
});
function parseCampaign(data) {
  const r = RawCampaignSchema.safeParse(data);
  if (!r.success) {
    throw new SchemaInvalid("Campaign JSON failed schema validation.", { issues: r.error.issues.slice(0, 5) });
  }
  return r.data;
}
function parseFindings(data) {
  const arr = Array.isArray(data) ? data : data?.data;
  const r = RawFindingArraySchema.safeParse(arr);
  if (!r.success) {
    throw new SchemaInvalid("Findings JSON failed schema validation.", { issues: r.error.issues.slice(0, 5) });
  }
  return r.data;
}
function parseMajor(version) {
  if (!version) return null;
  const m = String(version).match(/(\d+)/);
  return m ? Number(m[1]) : null;
}
function negotiateProVersion(version) {
  const major = parseMajor(version);
  if (major === null) {
    return { version: version ?? "unknown", major: 1 };
  }
  if (!SUPPORTED_API_MAJORS.includes(major)) {
    throw new UnsupportedVersion(
      `Darkmoon Pro API major v${major} is not supported by this client (supports v${SUPPORTED_API_MAJORS.join(", v")}).`,
      { version, supported: SUPPORTED_API_MAJORS }
    );
  }
  return { version: String(version), major };
}

// src/backends/pro-http.ts
var REPORT_PLACEHOLDER_PREFIX = "# Report not found";
var ProHttpBackend = class {
  constructor(cfg) {
    this.edition = "pro";
    this.mustChangePassword = false;
    this.cfg = cfg;
    this.base = cfg.baseUrl.replace(/\/+$/, "").replace(/\/api\/v1$/, "");
    this.apiBase = `${this.base}/api/v1`;
    this.token = cfg.token ?? null;
    this.log = cfg.logger ?? new Logger("warn");
  }
  async ensureAuth() {
    if (this.token) return;
    if (!this.cfg.username || !this.cfg.password) return;
    const res = await httpRequest(
      `${this.apiBase}/auth/login`,
      {
        method: "POST",
        body: { username: this.cfg.username, password: this.cfg.password },
        timeoutMs: this.cfg.timeoutMs,
        allowStatuses: [401]
      }
    );
    if (res.status === 401 || !res.data?.token) {
      throw new AuthError("Login rejected by the Pro API.", { url: safeUrl(`${this.apiBase}/auth/login`) });
    }
    this.mustChangePassword = Boolean(res.data.must_change_password ?? res.data.user?.must_change_password);
    if (this.mustChangePassword) {
      const msg = "Pro admin account still has its default password (must_change_password=true). Rotate it before using CI.";
      if (this.cfg.refuseInsecureDefault !== false) {
        throw new InsecureDefaultError(msg);
      }
      this.log.warn(msg);
    }
    if (typeof res.data.token !== "string") throw new SchemaInvalid("Login returned an invalid token.");
    this.token = res.data.token;
  }
  async detect() {
    const warnings = [];
    let features = {
      restApi: true,
      streaming: true,
      auth: true,
      remediation: true,
      dashboard: true,
      scheduler: true
    };
    let version = "unknown";
    let detectedBy = "root-probe";
    try {
      const info = await httpRequest(`${this.apiBase}/system/info`, { timeoutMs: this.cfg.timeoutMs, allowStatuses: [404] });
      const d = info.data;
      if (info.status !== 404 && d && (d.edition || d.api_version || d.version)) {
        version = String(d.api_version ?? d.version ?? "unknown");
        detectedBy = "system-info";
        if (d.features && typeof d.features === "object") {
          features = {
            restApi: true,
            streaming: Boolean(d.features.sse_progress ?? true),
            auth: Boolean(d.features.auth ?? true),
            remediation: Boolean(d.features.remediation ?? true),
            dashboard: true,
            scheduler: Boolean(d.features.scheduler ?? true)
          };
        }
        if (d.edition && String(d.edition).toLowerCase() !== "pro") {
          warnings.push(`system/info reports edition="${d.edition}", expected "pro".`);
        }
      } else {
        throw new Error("no system/info");
      }
    } catch {
      try {
        const root = await httpRequest(`${this.base}/`, { timeoutMs: this.cfg.timeoutMs });
        const svc = String(root.data?.service ?? "");
        if (!/darkmoon/i.test(svc)) {
          warnings.push(`Root service string "${svc}" does not look like a Darkmoon API.`);
        }
        version = String(root.data?.version ?? "unknown");
        detectedBy = "root-probe";
      } catch {
        throw new DarkmoonNotAvailable("Pro API root probe failed.", { url: safeUrl(this.base) });
      }
    }
    const negotiated = negotiateProVersion(version);
    if (this.mustChangePassword) {
      warnings.push("Pro admin still has must_change_password=true.");
    }
    return {
      edition: "pro",
      mode: "pro",
      version: negotiated.version,
      available: true,
      features,
      detectedBy,
      warnings
    };
  }
  async launchCampaign(input) {
    await this.ensureAuth();
    const nonce = input.program ?? `ci-${randomHex(8)}`;
    const body = {
      target: input.target,
      program: nonce,
      targets: input.targets,
      out_of_scope: input.outOfScope,
      exclude: input.exclude,
      focus: input.focus,
      credentials: input.credentials,
      tokens: input.tokens,
      noise: input.noise,
      severity: input.severity,
      format: input.format,
      rules: input.rules,
      safe_harbor: input.safeHarbor,
      remediate: input.remediate,
      git_repo: input.gitRepo,
      credential_id: input.credentialId,
      create_repo: input.createRepo
    };
    const res = await httpRequest(`${this.apiBase}/run/campaign`, {
      method: "POST",
      body,
      token: this.token,
      timeoutMs: this.cfg.timeoutMs
    });
    const identity = (value) => {
      if (value === void 0 || value === null) return null;
      if (typeof value !== "string" || !value.trim()) throw new SchemaInvalid("Launch returned an invalid identity.");
      return value;
    };
    const runId = identity(res.data?.run_id);
    const campaignId = identity(res.data?.campaign_id);
    if (!runId && !campaignId) throw new SchemaInvalid("Launch returned no run or campaign identity.");
    const correlation = {
      edition: "pro",
      runId,
      campaignId,
      nonce,
      preCampaignIds: [],
      startedAtMs: Date.now()
    };
    return { correlation, campaignId, runId };
  }
  /** Resolve explicit producer identity or a complete, unambiguous run-session binding. */
  async resolveCampaignId(ref) {
    await this.ensureAuth();
    const direct = refToId(ref);
    if (direct) return direct;
    if (typeof ref === "string") return ref;
    if (!ref.runId) return null;
    const run = await httpRequest(`${this.apiBase}/run/${encodeURIComponent(ref.runId)}`, {
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [404]
    });
    if (run.status !== 404) {
      const record = run.data?.data ?? run.data;
      if (!record || typeof record !== "object" || Array.isArray(record)) throw new SchemaInvalid("Run returned an invalid record.");
      const returnedRunId = record.run_id ?? record.id;
      if (returnedRunId !== void 0 && returnedRunId !== ref.runId) throw new CorrelationFailed("Run response identity does not match the request.");
      if (record.campaign_id !== void 0 && record.campaign_id !== null) {
        if (typeof record.campaign_id !== "string" || !record.campaign_id.trim()) throw new SchemaInvalid("Run returned an invalid campaign identity.");
        ref.campaignId = record.campaign_id;
        return ref.campaignId;
      }
      if (["succeeded", "failed", "timed_out", "interrupted", "cancelled", "aborted"].includes(record.status)) {
        throw new CorrelationFailed("Run ended without an associated campaign.");
      }
    }
    const logs = await httpRequest(`${this.apiBase}/run/logs/${encodeURIComponent(ref.runId)}`, {
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [404]
    });
    if (logs.status === 404) return null;
    if (!Array.isArray(logs.data?.data)) throw new SchemaInvalid("Run log response needs a data array.");
    const sid = extractSessionId(logs.data.data);
    if (!sid) return null;
    const exact = (await this.listCampaigns()).filter((c) => c.sessionId === sid || c.sessionId === sid.replace(/^ses_/, ""));
    if (exact.length > 1) throw new CorrelationFailed("Run session maps to multiple campaigns.");
    if (!exact.length) return null;
    ref.campaignId = exact[0].id;
    return ref.campaignId;
  }
  async getCampaignStatus(ref) {
    const id = await this.resolveCampaignId(ref);
    if (!id) {
      const runId = typeof ref === "string" ? null : ref.runId;
      return syntheticRunning(runId);
    }
    return this.getCampaign(id);
  }
  async listCampaigns(filter) {
    await this.ensureAuth();
    const qs = new URLSearchParams();
    if (filter?.targetId) qs.set("target_id", filter.targetId);
    if (filter?.status) qs.set("status", filter.status);
    const url = `${this.apiBase}/campaigns${qs.toString() ? `?${qs}` : ""}`;
    const res = await httpRequest(url, { token: this.token, timeoutMs: this.cfg.timeoutMs });
    const items = res.data?.data;
    if (!Array.isArray(items)) throw new SchemaInvalid("Campaign list response needs a data array.");
    return items.map((c) => normalizeCampaign(parseCampaign(c), "pro"));
  }
  async getCampaign(id) {
    await this.ensureAuth();
    const res = await httpRequest(`${this.apiBase}/campaigns/${encodeURIComponent(id)}`, {
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [404]
    });
    if (res.status === 404) {
      throw new CampaignNotFound(`Campaign ${id} not found.`, { id });
    }
    const raw = res.data?.data;
    if (!raw || typeof raw !== "object") throw new SchemaInvalid("Campaign detail response needs a data object.");
    if (raw.id !== id) throw new SchemaInvalid("Campaign detail identity does not match the request.");
    const campaign = normalizeCampaign(parseCampaign(raw), "pro");
    if (Array.isArray(raw.vulnerabilities)) {
      const findings = raw.vulnerabilities.map((v) => normalizeFinding(v, "pro"));
      campaign.severity = {
        critical: findings.filter((f) => f.severity === "critical").length,
        high: findings.filter((f) => f.severity === "high").length,
        medium: findings.filter((f) => f.severity === "medium").length,
        low: findings.filter((f) => f.severity === "low").length,
        info: findings.filter((f) => f.severity === "info").length,
        total: findings.length
      };
    }
    return campaign;
  }
  async listFindings(filter, opts) {
    await this.ensureAuth();
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries({
      campaign_id: filter.campaignId,
      project_id: filter.projectId,
      target_id: filter.targetId,
      severity: filter.severity,
      category: filter.category,
      status: filter.status
    })) {
      if (v) qs.set(k, String(v));
    }
    const url = `${this.apiBase}/vulnerabilities${qs.toString() ? `?${qs}` : ""}`;
    const res = await httpRequest(url, { token: this.token, timeoutMs: this.cfg.timeoutMs });
    const raws = parseFindings(res.data);
    let findings = raws.map((v) => normalizeFinding(v, "pro", { includeEvidence: opts?.includeEvidence, full: opts?.full }));
    findings = findings.filter((f) => matchesFindingFilter(f, filter));
    if (opts?.includeEvidence) {
      findings = await Promise.all(findings.map((f) => f.id ? this.getFinding(f.id, opts) : Promise.resolve(f)));
    }
    return findings;
  }
  async getFinding(id, opts) {
    await this.ensureAuth();
    const res = await httpRequest(`${this.apiBase}/vulnerabilities/${encodeURIComponent(id)}`, {
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [404]
    });
    if (res.status === 404) {
      throw new FindingNotFound(`Finding ${id} not found.`, { id });
    }
    const raw = parseFindings([res.data?.data])[0];
    const finding = normalizeFinding(raw, "pro", { includeEvidence: opts?.includeEvidence, full: opts?.full });
    if (finding.id !== id) throw new SchemaInvalid("Finding detail identity does not match the request.");
    return finding;
  }
  async getReport(campaignId) {
    await this.ensureAuth();
    const res = await httpRequest(
      `${this.apiBase}/campaigns/${encodeURIComponent(campaignId)}/report`,
      { token: this.token, timeoutMs: this.cfg.timeoutMs, allowStatuses: [404] }
    );
    if (res.status === 404) {
      throw new CampaignNotFound(`Campaign ${campaignId} not found.`, { id: campaignId });
    }
    if (typeof res.data?.content !== "string" || res.data.format !== void 0 && typeof res.data.format !== "string") throw new SchemaInvalid("Report response needs string content and format.");
    if (res.data.campaign_id !== void 0 && res.data.campaign_id !== campaignId) throw new SchemaInvalid("Report campaign identity does not match the request.");
    const content = res.data.content;
    const ready = content.length > 0 && !content.startsWith(REPORT_PLACEHOLDER_PREFIX);
    return { campaignId, format: res.data?.format ?? "markdown", content, ready };
  }
  async *streamProgress(ref) {
    await this.ensureAuth();
    const runId = typeof ref === "string" ? null : ref.runId;
    if (!runId) {
      throw new CorrelationFailed("streamProgress requires a Pro run id (launch the campaign via launchCampaign).");
    }
    for await (const evt of readSse(`${this.apiBase}/run/${encodeURIComponent(runId)}/stream`, { token: this.token, timeoutMs: this.cfg.timeoutMs })) {
      const e = evt;
      if (!e || typeof e !== "object" || typeof e.type !== "string" || !e.type) throw new SchemaInvalid("Run stream needs typed events.");
      if (e.run_id !== void 0 && e.run_id !== runId) throw new CorrelationFailed("Stream run identity does not match the request.");
      if (e.campaign_id !== void 0 && e.campaign_id !== null) {
        if (typeof e.campaign_id !== "string" || !e.campaign_id.trim()) throw new SchemaInvalid("Stream returned an invalid campaign identity.");
        if (typeof ref !== "string") {
          if (ref.campaignId && ref.campaignId !== e.campaign_id) throw new CorrelationFailed("Stream campaign identity conflicts with the launch.");
          ref.campaignId = e.campaign_id;
        }
      }
      const type = e.type;
      const terminal = type === "run_completed" || type === "run_error";
      yield {
        type,
        runId,
        campaignId: typeof ref === "string" ? null : ref.campaignId,
        message: typeof e?.text === "string" ? e.text : void 0,
        terminal,
        raw: e
      };
      if (terminal) return;
    }
    throw new NetworkError("Run stream closed before a terminal event; poll the run before assuming completion.");
  }
  // ── v0.2.0 additive surface ────────────────────────────────────────────
  /** GET with opt-in bounded retry on transient NETWORK/5xx (idempotent only). */
  async getWithRetry(url, allowStatuses) {
    await this.ensureAuth();
    const retries = Math.max(0, this.cfg.retries ?? 0);
    const base = this.cfg.backoffMs ?? 300;
    let lastErr;
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        return await httpRequest(url, { token: this.token, timeoutMs: this.cfg.timeoutMs, allowStatuses });
      } catch (err) {
        lastErr = err;
        const retryable = err instanceof NetworkError || err instanceof DarkmoonError && err.code === "NETWORK";
        if (!retryable || attempt === retries) break;
        const backoff = base * 2 ** attempt;
        await sleep(backoff + Math.random() * (backoff / 2));
      }
    }
    throw lastErr;
  }
  async registerWebhook(input) {
    await this.ensureAuth();
    const res = await httpRequest(`${this.apiBase}/webhooks`, {
      method: "POST",
      body: { url: input.url, events: input.events, secret: input.secret, format: input.format ?? "darkmoon" },
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [400]
    });
    if (res.status === 400 || !res.data?.data) {
      throw new DarkmoonError("BAD_REQUEST", `Webhook registration rejected: ${extractDetail(res) ?? "invalid url/events"}.`);
    }
    return mapWebhook(res.data.data);
  }
  async listWebhooks() {
    await this.ensureAuth();
    const res = await this.getWithRetry(`${this.apiBase}/webhooks`);
    return (res.data?.data ?? []).map(mapWebhook);
  }
  async deleteWebhook(id) {
    await this.ensureAuth();
    const res = await httpRequest(`${this.apiBase}/webhooks/${encodeURIComponent(id)}`, {
      method: "DELETE",
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [404]
    });
    return res.status !== 404;
  }
  async launchRetest(input) {
    await this.ensureAuth();
    const res = await httpRequest(`${this.apiBase}/retest`, {
      method: "POST",
      body: {
        target_id: input.targetId,
        campaign_id: input.campaignId,
        finding_ids: input.findingIds,
        safe_harbor: input.safeHarbor
      },
      token: this.token,
      timeoutMs: this.cfg.timeoutMs,
      allowStatuses: [400, 403, 404]
    });
    if (res.status === 403) throw new DarkmoonError("BAD_REQUEST", "Retest target is out of scope (allowlist).");
    if (res.status === 404) throw new CampaignNotFound("Base campaign for retest not found.");
    if (res.status === 400 || !res.data?.retest_id) {
      throw new DarkmoonError("BAD_REQUEST", `Retest launch rejected: ${extractDetail(res) ?? "target_id or campaign_id required"}.`);
    }
    return {
      retestId: res.data.retest_id,
      runId: res.data.run_id ?? null,
      baseCampaignId: res.data.base_campaign_id ?? null,
      targetId: res.data.target_id ?? null
    };
  }
  async getRetest(id) {
    const res = await this.getWithRetry(`${this.apiBase}/retest/${encodeURIComponent(id)}`, [404]);
    if (res.status === 404 || !res.data?.retest_id) {
      throw new DarkmoonError("BAD_REQUEST", `Retest ${id} not found.`, { id });
    }
    return mapRetest(res.data, "pro");
  }
  async getEvidenceMeta(id) {
    const res = await this.getWithRetry(`${this.apiBase}/vulnerabilities/${encodeURIComponent(id)}/evidence-meta`, [404]);
    if (res.status === 404 || !res.data) {
      throw new FindingNotFound(`Finding ${id} not found.`, { id });
    }
    const d = res.data;
    return {
      vulnId: d.vuln_id ?? id,
      hasEvidence: Boolean(d.has_evidence),
      counts: {
        commands: Number(d.counts?.commands ?? 0),
        payloads: Number(d.counts?.payloads ?? 0),
        screenshots: Number(d.counts?.screenshots ?? 0),
        logs: Number(d.counts?.logs ?? 0),
        requests: Number(d.counts?.requests ?? 0)
      },
      commandNames: Array.isArray(d.command_names) ? d.command_names.map(String) : [],
      hasScreenshot: Boolean(d.has_screenshot),
      hasExtractedData: Boolean(d.has_extracted_data),
      redacted: d.redacted !== false
    };
  }
  async getTimeseries(query = {}) {
    const qs = new URLSearchParams();
    qs.set("metric", query.metric ?? "severity");
    qs.set("group", query.group ?? "day");
    if (query.projectId) qs.set("project_id", query.projectId);
    if (query.targetId) qs.set("target_id", query.targetId);
    if (query.from) qs.set("from", query.from);
    if (query.to) qs.set("to", query.to);
    const res = await this.getWithRetry(`${this.apiBase}/metrics/timeseries?${qs}`, [400]);
    if (res.status === 400) throw new DarkmoonError("BAD_REQUEST", `Invalid timeseries query: ${extractDetail(res) ?? "bad metric/group"}.`);
    let series = Array.isArray(res.data?.series) ? res.data.series : [];
    const cap = this.cfg.pageSize ?? 0;
    if (cap > 0) series = series.slice(0, cap);
    return {
      metric: String(res.data?.metric ?? query.metric ?? "severity"),
      group: String(res.data?.group ?? query.group ?? "day"),
      series: series.map((s) => ({
        key: String(s.key),
        points: (s.points ?? []).map((p) => ({ t: String(p.t), value: Number(p.value ?? 0) }))
      })),
      edition: "pro"
    };
  }
  /**
   * Consolidated event stream via the Pro SSE feed (/events/stream), replayable
   * from the `since` cursor. Yields normalized DarkmoonEvents until the caller
   * breaks, the connection ends, or the AbortSignal fires.
   */
  async *streamEvents(opts = {}) {
    await this.ensureAuth();
    const qs = new URLSearchParams();
    qs.set("since", String(opts.since ?? 0));
    if (opts.events?.length) qs.set("events", opts.events.join(","));
    const url = `${this.apiBase}/events/stream?${qs}`;
    for await (const raw of readSse(url, { token: this.token, signal: opts.signal, timeoutMs: this.cfg.timeoutMs })) {
      const e = raw;
      if (!e || typeof e !== "object" || !e.event) continue;
      yield mapEvent(e);
    }
  }
};
function extractDetail(res) {
  const d = res.data?.detail;
  return typeof d === "string" ? d : null;
}
function mapWebhook(row) {
  return {
    id: String(row.id),
    url: String(row.url ?? ""),
    events: Array.isArray(row.events) ? row.events.map(String) : [],
    format: String(row.format ?? "darkmoon"),
    enabled: row.enabled !== false,
    createdAt: row.created_at ?? null,
    ...typeof row.secret === "string" ? { secret: row.secret } : {}
  };
}
function mapRetest(d, edition) {
  const summary = d.verdicts_summary ?? {};
  return {
    retestId: String(d.retest_id),
    baseCampaignId: d.base_campaign_id ?? null,
    newCampaignId: d.new_campaign_id ?? null,
    targetId: d.target_id ?? null,
    runId: d.run_id ?? null,
    status: d.status === "completed" ? "completed" : "running",
    verdictsSummary: {
      fixed: Number(summary.fixed ?? 0),
      still_present: Number(summary.still_present ?? 0),
      regressed: Number(summary.regressed ?? 0),
      new: Number(summary.new ?? 0)
    },
    findings: (d.findings ?? []).map((f) => ({
      findingId: f.finding_id ?? null,
      newFindingId: f.new_finding_id ?? null,
      baseStatus: f.base_status ?? null,
      newStatus: f.new_status ?? null,
      severity: f.severity ?? null,
      verdict: f.verdict
    })),
    edition
  };
}
function mapEvent(e) {
  return {
    event: String(e.event),
    contractVersion: String(e.contract_version ?? "1"),
    seq: Number(e.seq ?? 0),
    deliveryId: e.delivery_id ?? null,
    ts: e.ts ?? null,
    data: e.data && typeof e.data === "object" ? e.data : {}
  };
}
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
function syntheticRunning(runId) {
  return {
    id: runId ? `run:${runId}` : "run:pending",
    projectId: null,
    targetId: null,
    sessionId: null,
    target: null,
    status: "running",
    overallRisk: "none",
    createdAt: null,
    durationSeconds: null,
    reportPath: null,
    isSubagent: false,
    severity: { critical: 0, high: 0, medium: 0, low: 0, info: 0, total: 0 },
    executiveSummary: null,
    edition: "pro"
  };
}
function extractSessionId(events) {
  const sessions = /* @__PURE__ */ new Set();
  for (const e of events) {
    if (e?.type !== "run_started") continue;
    const sid = e.sessionID ?? e.session_id;
    if (typeof sid === "string" && sid.startsWith("ses_")) sessions.add(sid);
  }
  if (sessions.size > 1) throw new CorrelationFailed("Run log contains conflicting root session identities.");
  return [...sessions][0] ?? null;
}
function randomHex(n) {
  const bytes = new Uint8Array(Math.ceil(n / 2));
  import_node_crypto.webcrypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
}

// src/backends/oss-local.ts
var import_node_fs = require("fs");
var import_node_fs2 = require("fs");
var path = __toESM(require("path"), 1);
var os = __toESM(require("os"), 1);
var import_node_child_process = require("child_process");
var import_node_crypto2 = require("crypto");

// src/extensions-compute.ts
var CLOSED = /* @__PURE__ */ new Set(["remediated", "resolved", "closed", "fixed"]);
function norm(s) {
  return String(s ?? "").trim().toLowerCase();
}
function findingKey(f) {
  return [norm(f.title), norm(f.endpoint), norm(f.category)].join("|");
}
function evidenceMetaFromFinding(vulnId, f) {
  const ev = f?.evidence ?? null;
  const commands = ev?.commands ?? [];
  const payloads = ev?.payloads ?? [];
  const logs = ev?.logs ?? [];
  const requestCount = (ev?.rawRequest ? 1 : 0) + (ev?.rawResponse ? 1 : 0);
  const commandNames = commands.map((c) => norm(c).split(/\s+/)[0] ?? "").filter(Boolean).slice(0, 50);
  return {
    vulnId,
    hasEvidence: Boolean(ev),
    counts: {
      commands: commands.length,
      payloads: payloads.length,
      screenshots: 0,
      // OSS evidence has no dedicated screenshot list in the normalized shape
      logs: logs.length,
      requests: requestCount
    },
    commandNames: Array.from(new Set(commandNames)),
    hasScreenshot: false,
    hasExtractedData: Boolean(ev?.extractedData),
    redacted: true
  };
}
function computeRetestVerdicts(base, next, findingIds) {
  let baseSet = base;
  if (findingIds?.length) {
    const wanted = new Set(findingIds);
    baseSet = base.filter((f) => f.id && wanted.has(f.id));
  }
  const nextByKey = /* @__PURE__ */ new Map();
  for (const f of next) if (!nextByKey.has(findingKey(f))) nextByKey.set(findingKey(f), f);
  const results = [];
  const baseKeys = /* @__PURE__ */ new Set();
  for (const f of baseSet) {
    const key = findingKey(f);
    baseKeys.add(key);
    const baseStatus = norm(f.status) || "unconfirmed";
    const match = nextByKey.get(key);
    if (match) {
      results.push({
        findingId: f.id ?? null,
        newFindingId: match.id ?? null,
        baseStatus,
        newStatus: norm(match.status) || "unconfirmed",
        severity: match.severity ?? f.severity ?? null,
        verdict: CLOSED.has(baseStatus) ? "regressed" : "still_present"
      });
    } else {
      results.push({
        findingId: f.id ?? null,
        newFindingId: null,
        baseStatus,
        newStatus: null,
        severity: f.severity ?? null,
        verdict: "fixed"
      });
    }
  }
  for (const f of next) {
    if (!baseKeys.has(findingKey(f))) {
      results.push({
        findingId: null,
        newFindingId: f.id ?? null,
        baseStatus: null,
        newStatus: norm(f.status) || "unconfirmed",
        severity: f.severity ?? null,
        verdict: "new"
      });
    }
  }
  return results;
}
function summarizeVerdicts(findings) {
  const summary = { fixed: 0, still_present: 0, regressed: 0, new: 0 };
  for (const f of findings) summary[f.verdict] += 1;
  return summary;
}

// src/backends/oss-local.ts
var RUNNING_STATUSES = /* @__PURE__ */ new Set(["running", "queued", "unknown"]);
var OssLocalBackend = class {
  constructor(cfg) {
    this.edition = "oss";
    /** In-process retest tracking (OSS is stateless across runs; best-effort). */
    this.retests = /* @__PURE__ */ new Map();
    this.cfg = cfg;
    this.log = cfg.logger ?? new Logger("warn");
    this.campaignsDir = path.join(cfg.dataDir, "campaigns");
    this.vulnsDir = path.join(cfg.dataDir, "vulnerabilities");
    this.reportsDir = cfg.reportsDir ?? path.join(cfg.dataDir, "reports");
    this.scriptPath = cfg.scriptPath ?? path.join(os.homedir(), "darkmoon.sh");
  }
  async detect() {
    const warnings = [];
    const hasData = (0, import_node_fs2.existsSync)(this.campaignsDir);
    if (!hasData) {
      throw new DarkmoonNotAvailable(`OSS data dir not found: ${this.campaignsDir}`, { dataDir: this.cfg.dataDir });
    }
    const hasScript = this.cfg.launchTemplate ? true : (0, import_node_fs2.existsSync)(this.scriptPath);
    if (!hasScript) {
      warnings.push(`darkmoon.sh not found at ${this.scriptPath}; read operations work, launchCampaign will fail.`);
    }
    let version = "unknown";
    for (const f of ["VERSION", "version.txt", ".darkmoon-version"]) {
      const p = path.join(this.cfg.dataDir, f);
      if ((0, import_node_fs2.existsSync)(p)) {
        try {
          version = (await import_node_fs.promises.readFile(p, "utf8")).trim() || "unknown";
        } catch {
        }
        break;
      }
    }
    return {
      edition: "oss",
      mode: "oss",
      version,
      available: true,
      features: { restApi: false, streaming: false, auth: false, remediation: false, dashboard: false, scheduler: false },
      detectedBy: "cli-probe",
      warnings
    };
  }
  buildPrompt(input, nonce) {
    const parts = [`TARGET: ${input.target}`, `PROGRAM=${nonce}`];
    if (input.targets?.length) parts.push(`TARGETS=${input.targets.join(",")}`);
    if (input.outOfScope?.length) parts.push(`OUT=${input.outOfScope.join(",")}`);
    if (input.exclude?.length) parts.push(`EXCLUDE=${input.exclude.join(",")}`);
    if (input.focus?.length) parts.push(`FOCUS=${input.focus.join(",")}`);
    if (input.credentials?.length) parts.push(`CREDS=${input.credentials.join(",")}`);
    if (input.tokens?.length) parts.push(`TOKEN=${input.tokens.join(",")}`);
    if (input.noise) parts.push(`NOISE=${input.noise}`);
    if (input.severity) parts.push(`SEVERITY=${input.severity}`);
    if (input.format) parts.push(`FORMAT=${input.format}`);
    if (input.rules?.length) parts.push(`RULES="${input.rules.join(";")}"`);
    if (input.safeHarbor) parts.push(`SAFE_HARBOR=${input.safeHarbor}`);
    return parts.join(" ");
  }
  async launchCampaign(input) {
    const nonce = input.program ?? `ci-${randomHex2(8)}`;
    const prompt = this.buildPrompt(input, nonce);
    const preCampaignIds = await this.listCampaignIds();
    let cmd;
    let args;
    if (this.cfg.launchTemplate?.length) {
      const tpl = this.cfg.launchTemplate.map((a) => a === "{PROMPT}" ? prompt : a);
      cmd = tpl[0];
      args = tpl.slice(1);
    } else {
      if (!(0, import_node_fs2.existsSync)(this.scriptPath)) {
        throw new DarkmoonNotAvailable(`darkmoon.sh not found at ${this.scriptPath}.`);
      }
      cmd = this.scriptPath;
      args = [prompt];
    }
    const child = (0, import_node_child_process.spawn)(cmd, args, {
      cwd: this.cfg.cwd ?? path.dirname(this.scriptPath),
      env: process.env,
      detached: true,
      stdio: "ignore"
    });
    child.unref();
    const correlation = {
      edition: "oss",
      runId: null,
      campaignId: null,
      nonce,
      preCampaignIds,
      startedAtMs: Date.now()
    };
    this.log.info(`OSS campaign launched (nonce=${nonce}, pid=${child.pid ?? "?"}). Correlation deferred.`);
    return { correlation, campaignId: null, runId: null };
  }
  async listCampaignIds() {
    try {
      const files = await import_node_fs.promises.readdir(this.campaignsDir);
      return files.filter((f) => f.endsWith(".json")).map((f) => f.replace(/\.json$/, ""));
    } catch {
      return [];
    }
  }
  async resolveCampaignId(ref) {
    const direct = refToId(ref);
    if (direct) return direct;
    if (typeof ref === "string") return ref;
    if (ref.campaignId) return ref.campaignId;
    const pre = new Set(ref.preCampaignIds ?? []);
    let files;
    try {
      files = (await import_node_fs.promises.readdir(this.campaignsDir)).filter((f) => f.endsWith(".json") && f !== "unknown.json");
    } catch {
      return null;
    }
    const fresh = [];
    for (const f of files) {
      const id = f.replace(/\.json$/, "");
      if (pre.has(id)) continue;
      try {
        const st = await import_node_fs.promises.stat(path.join(this.campaignsDir, f));
        if (st.mtimeMs >= ref.startedAtMs - 2e3) fresh.push({ id, mtimeMs: st.mtimeMs });
      } catch {
      }
    }
    if (fresh.length === 0) return null;
    if (fresh.length === 1) {
      ref.campaignId = fresh[0].id;
      return fresh[0].id;
    }
    // Sorting by mtime is not an exact run identity. Fail closed if another
    // process created a candidate campaign concurrently.
    throw new CorrelationFailed("Multiple new OSS campaigns match this launch; identity is ambiguous.");
  }
  async readCampaignFile(id) {
    const p = path.join(this.campaignsDir, `${id}.json`);
    if (!(0, import_node_fs2.existsSync)(p)) return null;
    try {
      return JSON.parse(await import_node_fs.promises.readFile(p, "utf8"));
    } catch {
      return null;
    }
  }
  async readFindingsFile(campaignId) {
    const p = path.join(this.vulnsDir, `${campaignId}.json`);
    // A missing/unreadable/corrupt journal is NOT a successful empty scan.
    // Legitimate zero findings must be represented by a readable JSON [].
    let raw;
    try {
      raw = JSON.parse(await import_node_fs.promises.readFile(p, "utf8"));
    } catch {
      throw new SchemaInvalid("Campaign findings are unavailable or malformed.");
    }
    if (!Array.isArray(raw)) throw new SchemaInvalid("Campaign findings must be a JSON array.");
    const findings = parseFindings(raw);
    // Never let a campaign-qualified read quietly filter out a foreign or
    // missing campaign_id and misreport it as a clean zero-finding result.
    if (findings.some((finding) => finding.campaign_id !== campaignId)) {
      throw new SchemaInvalid("Campaign findings contain a foreign or missing campaign identity.");
    }
    return findings;
  }
  async getCampaign(id) {
    const raw = await this.readCampaignFile(id);
    if (!raw) throw new CampaignNotFound(`Campaign ${id} not found in ${this.campaignsDir}.`, { id });
    const campaign = normalizeCampaign(parseCampaign(raw), "oss");
    const raws = await this.readFindingsFile(id);
    if (raws.length > 0) {
      const findings = raws.map((v) => normalizeFinding(v, "oss"));
      campaign.severity = severitySummaryFromFindings(findings);
    }
    return campaign;
  }
  async getCampaignStatus(ref) {
    const id = await this.resolveCampaignId(ref);
    if (!id) {
      return {
        id: typeof ref === "string" ? ref : `oss:pending:${ref.nonce ?? ""}`,
        projectId: null,
        targetId: null,
        sessionId: null,
        target: null,
        status: "running",
        overallRisk: "none",
        createdAt: null,
        durationSeconds: null,
        reportPath: null,
        isSubagent: false,
        severity: { critical: 0, high: 0, medium: 0, low: 0, info: 0, total: 0 },
        executiveSummary: null,
        edition: "oss"
      };
    }
    return this.getCampaign(id);
  }
  async listCampaigns(filter) {
    let files;
    try {
      files = (await import_node_fs.promises.readdir(this.campaignsDir)).filter((f) => f.endsWith(".json") && f !== "unknown.json");
    } catch {
      return [];
    }
    const out2 = [];
    for (const f of files) {
      const raw = await this.readCampaignFile(f.replace(/\.json$/, ""));
      if (!raw) continue;
      if (raw.is_subagent) continue;
      const c = normalizeCampaign(parseCampaign(raw), "oss");
      if (filter?.targetId && c.targetId !== filter.targetId) continue;
      if (filter?.status && c.status !== filter.status) continue;
      out2.push(c);
    }
    return out2;
  }
  async listFindings(filter, opts) {
    let campaignIds;
    if (filter.campaignId) {
      campaignIds = [filter.campaignId];
    } else {
      try {
        campaignIds = (await import_node_fs.promises.readdir(this.vulnsDir)).filter((f) => f.endsWith(".json")).map((f) => f.replace(/\.json$/, ""));
      } catch {
        campaignIds = [];
      }
    }
    const out2 = [];
    for (const cid of campaignIds) {
      const raws = await this.readFindingsFile(cid);
      for (const v of raws) {
        const f = normalizeFinding(v, "oss", { includeEvidence: opts?.includeEvidence, full: opts?.full });
        if (matchesFindingFilter(f, filter)) out2.push(f);
      }
    }
    return out2;
  }
  async getFinding(id, opts) {
    let files;
    try {
      files = (await import_node_fs.promises.readdir(this.vulnsDir)).filter((f) => f.endsWith(".json"));
    } catch {
      files = [];
    }
    for (const f of files) {
      const raws = await this.readFindingsFile(f.replace(/\.json$/, ""));
      const hit = raws.find((v) => String(v.id ?? v.node_id ?? "") === id);
      if (hit) return normalizeFinding(hit, "oss", { includeEvidence: opts?.includeEvidence, full: opts?.full });
    }
    throw new FindingNotFound(`Finding ${id} not found.`, { id });
  }
  /** Map a container report_path (/reports/x.md) to the host reports dir. */
  resolveReportPath(reportPath) {
    if (!reportPath) return null;
    const base = path.basename(reportPath);
    const candidate = path.join(this.reportsDir, base);
    if ((0, import_node_fs2.existsSync)(candidate)) return candidate;
    if ((0, import_node_fs2.existsSync)(reportPath)) return reportPath;
    return null;
  }
  async newestReport() {
    try {
      const files = (await import_node_fs.promises.readdir(this.reportsDir)).filter((f) => f.endsWith(".md"));
      let newest = null;
      for (const f of files) {
        const p = path.join(this.reportsDir, f);
        const st = await import_node_fs.promises.stat(p);
        if (!newest || st.mtimeMs > newest.mtimeMs) newest = { p, mtimeMs: st.mtimeMs };
      }
      return newest?.p ?? null;
    } catch {
      return null;
    }
  }
  async getReport(campaignId) {
    const raw = await this.readCampaignFile(campaignId);
    if (!raw) throw new CampaignNotFound(`Campaign ${campaignId} not found.`, { id: campaignId });
    let file = this.resolveReportPath(raw.report_path ?? null);
    if (!file) file = await this.newestReport();
    if (!file) {
      return { campaignId, format: "markdown", content: "", ready: false };
    }
    const content = await import_node_fs.promises.readFile(file, "utf8");
    const ready = content.trim().length > 0;
    return { campaignId, format: "markdown", content, ready };
  }
  /**
   * OSS has no live event stream. We emit a synthetic poll-based progress stream:
   * poll the campaign status until it reaches a terminal state.
   */
  async *streamProgress(ref) {
    const pollMs = 5e3;
    let lastStatus = "";
    for (; ; ) {
      let campaign = null;
      try {
        campaign = await this.getCampaignStatus(ref);
      } catch {
        campaign = null;
      }
      const status = campaign?.status ?? "running";
      if (status !== lastStatus) {
        lastStatus = status;
        yield {
          type: "status",
          campaignId: campaign?.id ?? null,
          message: `campaign status: ${status}`,
          terminal: !RUNNING_STATUSES.has(status),
          raw: { status }
        };
      }
      if (campaign && !RUNNING_STATUSES.has(status)) return;
      await sleep2(pollMs);
    }
  }
  // ── v0.2.0 additive surface (graceful OSS degradation) ──────────────────
  // OSS ships NO API server, so outbound webhooks cannot be dispatched. We fail
  // loudly with NOT_SUPPORTED rather than pretend — integrations branch on the
  // code and fall back to the polling event stream below.
  async registerWebhook(_input) {
    throw new NotSupported("Webhooks require Darkmoon Pro (OSS runs no server). Use streamEvents() polling instead.");
  }
  async listWebhooks() {
    throw new NotSupported("Webhooks require Darkmoon Pro (OSS runs no server).");
  }
  async deleteWebhook(_id) {
    throw new NotSupported("Webhooks require Darkmoon Pro (OSS runs no server).");
  }
  /** OSS retest = launch a fresh campaign on the base scope; verdict computed client-side. */
  async launchRetest(input) {
    let baseCampaignId = input.campaignId ?? null;
    let targetId = null;
    let targetHost = null;
    if (baseCampaignId) {
      const base = await this.getCampaign(baseCampaignId);
      targetId = base.targetId;
      targetHost = base.target;
    } else if (input.targetId) {
      const campaigns = (await this.listCampaigns({ targetId: input.targetId })).sort((a, b) => String(a.createdAt ?? "").localeCompare(String(b.createdAt ?? "")));
      const base = campaigns[campaigns.length - 1];
      if (!base) throw new CampaignNotFound(`No prior campaign for target ${input.targetId}.`);
      baseCampaignId = base.id;
      targetId = base.targetId;
      targetHost = base.target;
    } else {
      throw new NotSupported("launchRetest requires targetId or campaignId.");
    }
    if (!targetHost) throw new CampaignNotFound("Cannot resolve target host to retest.");
    const launched = await this.launchCampaign({ target: targetHost, safeHarbor: input.safeHarbor ?? "non-destructive" });
    const retestId = `retest_${randomHex2(8)}`;
    this.retests.set(retestId, {
      baseCampaignId,
      targetId,
      correlation: launched.correlation,
      findingIds: input.findingIds
    });
    return { retestId, runId: launched.runId, baseCampaignId, targetId };
  }
  async getRetest(id) {
    const rec = this.retests.get(id);
    if (!rec) throw new NotSupported(`Retest ${id} is not tracked in this process (OSS retests are in-memory).`);
    const newCampaignId = await this.resolveCampaignId(rec.correlation);
    let status = "running";
    let findings = [];
    if (newCampaignId) {
      const newCampaign = await this.getCampaign(newCampaignId).catch(() => null);
      if (newCampaign && !RUNNING_STATUSES.has(newCampaign.status)) status = "completed";
      const base = await this.listFindings({ campaignId: rec.baseCampaignId }, { includeEvidence: false });
      const next = await this.listFindings({ campaignId: newCampaignId }, { includeEvidence: false });
      findings = computeRetestVerdicts(base, next, rec.findingIds);
    }
    return {
      retestId: id,
      baseCampaignId: rec.baseCampaignId,
      newCampaignId,
      targetId: rec.targetId,
      runId: rec.correlation.runId,
      status,
      verdictsSummary: summarizeVerdicts(findings),
      findings,
      edition: "oss"
    };
  }
  async getEvidenceMeta(id) {
    const finding = await this.getFinding(id, { includeEvidence: true }).catch(() => null);
    if (!finding) throw new FindingNotFound(`Finding ${id} not found.`, { id });
    return evidenceMetaFromFinding(id, finding);
  }
  async getTimeseries(query = {}) {
    const metric = query.metric ?? "severity";
    const group = query.group ?? "day";
    let campaigns = await this.listCampaigns();
    if (query.projectId) campaigns = campaigns.filter((c) => c.projectId === query.projectId);
    if (query.targetId) campaigns = campaigns.filter((c) => c.targetId === query.targetId);
    if (query.from) campaigns = campaigns.filter((c) => String(c.createdAt ?? "").slice(0, 10) >= query.from);
    if (query.to) campaigns = campaigns.filter((c) => String(c.createdAt ?? "").slice(0, 10) <= query.to);
    campaigns.sort((a, b) => String(a.createdAt ?? "").localeCompare(String(b.createdAt ?? "")));
    const buckets = [];
    const grid = /* @__PURE__ */ new Map();
    const keys = [];
    const add = (b, key) => {
      if (!grid.has(b)) {
        grid.set(b, /* @__PURE__ */ new Map());
        buckets.push(b);
      }
      const row = grid.get(b);
      row.set(key, (row.get(key) ?? 0) + 1);
      if (!keys.includes(key)) keys.push(key);
    };
    for (const c of campaigns) {
      const b = group === "campaign" ? c.id : String(c.createdAt ?? "").slice(0, 10) || "unknown";
      if (metric === "campaigns") {
        add(b, "campaigns");
        continue;
      }
      const fs3 = await this.listFindings({ campaignId: c.id }, { includeEvidence: false });
      for (const f of fs3) {
        const value = metric === "severity" ? f.severity : metric === "status" ? f.status : f.category ?? "unknown";
        add(b, String(value ?? "unknown").toLowerCase());
      }
    }
    return {
      metric,
      group,
      edition: "oss",
      series: keys.map((key) => ({ key, points: buckets.map((b) => ({ t: b, value: grid.get(b)?.get(key) ?? 0 })) }))
    };
  }
  /**
   * OSS has no event bus. We synthesize the same event taxonomy by polling the
   * data dir and diffing campaigns/findings, so a trigger works identically
   * (graceful degradation). Yields until the AbortSignal fires.
   */
  async *streamEvents(opts = {}) {
    const pollMs = opts.pollIntervalMs ?? 5e3;
    const wanted = opts.events?.length ? new Set(opts.events) : null;
    let seq = opts.since ?? 0;
    const seenCampaign = /* @__PURE__ */ new Map();
    const seenFinding = /* @__PURE__ */ new Map();
    let first = true;
    const emit = (event, data) => {
      if (wanted && !wanted.has(event)) return null;
      return { event, contractVersion: "1", seq: ++seq, deliveryId: null, ts: (/* @__PURE__ */ new Date()).toISOString(), data };
    };
    for (; ; ) {
      if (opts.signal?.aborted) return;
      const campaigns = await this.listCampaigns().catch(() => []);
      for (const c of campaigns) {
        const prev = seenCampaign.get(c.id);
        const findings = await this.listFindings({ campaignId: c.id }, { includeEvidence: false }).catch(() => []);
        if (prev === void 0) {
          if (!first) {
            if (c.status === "running") {
              const e = emit("campaign.started", { campaign_id: c.id, target_id: c.targetId, status: c.status });
              if (e) yield e;
            }
            if (["completed", "stopped", "failed"].includes(c.status)) {
              const e = emit(`campaign.${c.status === "failed" ? "aborted" : c.status}`, { campaign_id: c.id, target_id: c.targetId, status: c.status });
              if (e) yield e;
            }
          }
        } else if (prev !== c.status && ["completed", "stopped", "failed"].includes(c.status)) {
          const e = emit(`campaign.${c.status === "failed" ? "aborted" : c.status}`, { campaign_id: c.id, target_id: c.targetId, status: c.status });
          if (e) yield e;
        }
        seenCampaign.set(c.id, c.status);
        for (const f of findings) {
          if (!f.id) continue;
          const prevF = seenFinding.get(f.id);
          if (prevF === void 0) {
            if (!first) {
              const e = emit("finding.discovered", safeFindingData(f, c.id));
              if (e) yield e;
              if (["confirmed", "exploited", "remediated"].includes(f.status)) {
                const e2 = emit(`finding.${f.status}`, safeFindingData(f, c.id));
                if (e2) yield e2;
              }
            }
          } else if (prevF !== f.status && ["confirmed", "exploited", "remediated"].includes(f.status)) {
            const e = emit(`finding.${f.status}`, safeFindingData(f, c.id));
            if (e) yield e;
          }
          seenFinding.set(f.id, f.status);
        }
      }
      first = false;
      await sleep2(pollMs);
    }
  }
};
function safeFindingData(f, campaignId) {
  return {
    finding_id: f.id,
    campaign_id: campaignId,
    target_id: f.targetId,
    title: f.title,
    severity: f.severity,
    status: f.status,
    category: f.category,
    cve: f.cve,
    cvss_score: f.cvssScore,
    endpoint: f.endpoint,
    has_evidence: f.evidence != null
  };
}
function randomHex2(n) {
  const bytes = new Uint8Array(Math.ceil(n / 2));
  import_node_crypto2.webcrypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
}
function sleep2(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// src/client.ts
var TERMINAL = /* @__PURE__ */ new Set(["completed", "stopped", "failed"]);
var STUCK = /* @__PURE__ */ new Set(["running", "queued", "unknown"]);
var DarkmoonClient = class _DarkmoonClient {
  constructor(cfg = {}) {
    this.backend = null;
    this.caps = null;
    this.cfg = cfg;
    this.log = cfg.logger ?? new Logger(cfg.logLevel ?? "warn");
  }
  /** Detect the active backend (cached). Applies the mode override. */
  async detect() {
    if (this.caps) return this.caps;
    const mode = this.cfg.mode ?? "auto";
    if (mode === "pro") {
      this.backend = this.makePro();
      this.caps = await this.backend.detect();
      return this.caps;
    }
    if (mode === "oss") {
      this.backend = this.makeOss();
      this.caps = await this.backend.detect();
      return this.caps;
    }
    const errors = [];
    if (this.cfg.pro) {
      try {
        const pro = this.makePro();
        const caps = await pro.detect();
        this.backend = pro;
        this.caps = caps;
        return caps;
      } catch (err) {
        errors.push(`pro: ${err.message}`);
      }
    }
    if (this.cfg.oss) {
      try {
        const oss = this.makeOss();
        const caps = await oss.detect();
        this.backend = oss;
        this.caps = caps;
        return caps;
      } catch (err) {
        errors.push(`oss: ${err.message}`);
      }
    }
    throw new DarkmoonNotAvailable(
      `No Darkmoon backend reachable in auto mode. ${errors.join("; ") || "No pro/oss config provided."}`
    );
  }
  makePro() {
    if (!this.cfg.pro) throw new DarkmoonNotAvailable("Pro mode selected but no `pro` config was provided.");
    return new ProHttpBackend({ ...this.cfg.pro, logger: this.log });
  }
  makeOss() {
    if (!this.cfg.oss) throw new DarkmoonNotAvailable("OSS mode selected but no `oss` config was provided.");
    return new OssLocalBackend({ ...this.cfg.oss, logger: this.log });
  }
  async be() {
    if (!this.backend) await this.detect();
    return this.backend;
  }
  /** The resolved edition (after detect). */
  get edition() {
    return this.caps?.edition ?? null;
  }
  async launchCampaign(input) {
    if (!input?.target) throw new DarkmoonError("BAD_REQUEST", "launchCampaign requires a `target`.");
    return (await this.be()).launchCampaign(input);
  }
  static toHandle(ref) {
    if (typeof ref === "string") return ref;
    if ("correlation" in ref) return ref.correlation;
    return ref;
  }
  async getCampaignStatus(ref) {
    return (await this.be()).getCampaignStatus(_DarkmoonClient.toHandle(ref));
  }
  async listCampaigns(filter) {
    return (await this.be()).listCampaigns(filter);
  }
  async getCampaign(id) {
    const be = await this.be();
    const handle = _DarkmoonClient.toHandle(id);
    const cid = typeof handle === "string" ? handle : await be.resolveCampaignId(handle);
    if (!cid) throw new DarkmoonError("CAMPAIGN_NOT_FOUND", "Campaign reference could not be resolved to an id.");
    return be.getCampaign(cid);
  }
  async listFindings(filter, opts) {
    _DarkmoonClient.assertFullOptIn(opts);
    return (await this.be()).listFindings(filter, opts);
  }
  async getFinding(id, opts) {
    _DarkmoonClient.assertFullOptIn(opts);
    return (await this.be()).getFinding(id, opts);
  }
  async getSeveritySummary(campaign) {
    const c = await this.getCampaign(campaign);
    return c.severity;
  }
  async getReport(campaign, opts) {
    const be = await this.be();
    const handle = _DarkmoonClient.toHandle(campaign);
    const cid = typeof handle === "string" ? handle : await be.resolveCampaignId(handle);
    if (!cid) throw new DarkmoonError("CAMPAIGN_NOT_FOUND", "Campaign reference could not be resolved to an id.");
    const raw = await be.getReport(cid);
    if (!raw.ready) {
      throw new ReportNotReady(`Report for ${cid} is not ready yet (placeholder or empty).`, { campaignId: cid });
    }
    const wantFull = Boolean(opts?.full);
    if (wantFull && !opts?.private) {
      throw new DarkmoonError(
        "BAD_REQUEST",
        "getReport({ full: true }) also requires `private: true` \u2014 the full report contains rehydrated real values and must not be emitted to CI logs/artifacts by accident."
      );
    }
    const content = wantFull ? raw.content : redactReport(raw.content);
    return { campaignId: cid, format: raw.format, content, ready: true, redacted: !wantFull };
  }
  /**
   * Poll until the campaign reaches a terminal state. Enforces a HARD timeout:
   * a campaign still running/unknown past `timeoutMs` is treated as a FAILURE
   * (StuckCampaignError), never a pass. We NEVER derive pass/fail from an exit
   * code — status and findings are the source of truth.
   */
  async waitForCompletion(ref, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? 60 * 60 * 1e3;
    const pollIntervalMs = opts.pollIntervalMs ?? 5e3;
    const failOnStuck = opts.failOnStuck ?? true;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isFinite(pollIntervalMs) || pollIntervalMs <= 0) {
      throw new DarkmoonError("BAD_REQUEST", "Timeout and poll interval must be positive finite durations.");
    }
    const deadline = Date.now() + timeoutMs;
    const be = await this.be();
    const handle = _DarkmoonClient.toHandle(ref);
    let last = null;
    for (; ; ) {
      const c = await be.getCampaignStatus(handle);
      if (!last || last.status !== c.status) {
        opts.onProgress?.(c);
        last = c;
      }
      if (TERMINAL.has(c.status)) return c;
      if (Date.now() >= deadline) {
        if (failOnStuck && STUCK.has(c.status)) {
          throw new StuckCampaignError(
            `Campaign ${c.id} still '${c.status}' after ${Math.round(timeoutMs / 1e3)}s \u2014 treating as failure.`,
            { campaignId: c.id, status: c.status }
          );
        }
        return c;
      }
      await sleep3(Math.min(pollIntervalMs, Math.max(0, deadline - Date.now())));
    }
  }
  async *streamProgress(ref) {
    const be = await this.be();
    yield* be.streamProgress(_DarkmoonClient.toHandle(ref));
  }
  // ── v0.2.0 additive surface (Phase-2 integrations) ─────────────────────
  // Delegates to the active backend. OSS degrades gracefully (webhooks throw
  // NOT_SUPPORTED; retest/events/timeseries computed client-side).
  async registerWebhook(input) {
    if (!input?.url) throw new DarkmoonError("BAD_REQUEST", "registerWebhook requires a `url`.");
    return (await this.be()).registerWebhook(input);
  }
  async listWebhooks() {
    return (await this.be()).listWebhooks();
  }
  async deleteWebhook(id) {
    if (!id) throw new DarkmoonError("BAD_REQUEST", "deleteWebhook requires an id.");
    return (await this.be()).deleteWebhook(id);
  }
  async launchRetest(input) {
    if (!input?.targetId && !input?.campaignId) {
      throw new DarkmoonError("BAD_REQUEST", "launchRetest requires `targetId` or `campaignId`.");
    }
    return (await this.be()).launchRetest(input);
  }
  async getRetest(id) {
    if (!id) throw new DarkmoonError("BAD_REQUEST", "getRetest requires a retest id.");
    return (await this.be()).getRetest(id);
  }
  async getEvidenceMeta(id) {
    if (!id) throw new DarkmoonError("BAD_REQUEST", "getEvidenceMeta requires a finding id.");
    return (await this.be()).getEvidenceMeta(id);
  }
  async getTimeseries(query) {
    return (await this.be()).getTimeseries(query);
  }
  async *streamEvents(opts) {
    yield* (await this.be()).streamEvents(opts);
  }
  static assertFullOptIn(opts) {
    if (opts?.full && !opts?.private) {
      throw new DarkmoonError(
        "BAD_REQUEST",
        "Evidence `full: true` also requires `private: true` (internal-only opt-in for rehydrated real values)."
      );
    }
  }
};
function sleep3(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// src/fail-policy.ts
function parseFailOn(input) {
  if (!input) return ["critical", "high"];
  const list = Array.isArray(input) ? input : input.split(",");
  const out2 = /* @__PURE__ */ new Set();
  for (const raw of list) {
    const t = raw.trim().toLowerCase();
    if (!t) continue;
    if (t === "none") return [];
    if (t === "all" || t === "any") return [...SEVERITIES];
    out2.add(normalizeSeverity(t));
  }
  return [...out2];
}
function computeFailPolicy(input, failOn) {
  const severities = Array.isArray(failOn) ? failOn : parseFailOn(failOn);
  const summary = Array.isArray(input) ? summarize(input) : input;
  const offending = {};
  let failed = false;
  for (const sev of severities) {
    const n = summary[sev];
    if (n > 0) {
      offending[sev] = n;
      failed = true;
    }
  }
  const reason = failed ? `Fail policy tripped: ${Object.entries(offending).map(([s, n]) => `${n} ${s}`).join(", ")} (fail-on: ${severities.join(", ") || "none"}).` : `No findings at or above the fail threshold (fail-on: ${severities.join(", ") || "none"}).`;
  return { failed, exitCode: failed ? 2 : 0, failOn: severities, offending, reason };
}
function summarize(findings) {
  const s = { critical: 0, high: 0, medium: 0, low: 0, info: 0, total: 0 };
  for (const f of findings) {
    s[f.severity] += 1;
    s.total += 1;
  }
  return s;
}

// cli/darkmoon-ci.ts
var EXIT_OK = 0;
var EXIT_ERROR = 1;
var EXIT_POLICY = 2;
function env(name) {
  const v = process.env[name];
  return v && v.length ? v : void 0;
}
function buildConfig(opts) {
  const mode = opts.mode ?? env("DARKMOON_MODE") ?? "auto";
  const proUrl = opts["pro-url"] ?? env("DARKMOON_PRO_URL");
  const ossData = opts["oss-data-dir"] ?? env("DARKMOON_OSS_DATA_DIR");
  const cfg = { mode, logLevel: opts.verbose ? "debug" : "warn" };
  if (proUrl) {
    cfg.pro = {
      baseUrl: proUrl,
      username: opts["pro-user"] ?? env("DARKMOON_PRO_USER"),
      password: opts["pro-pass"] ?? env("DARKMOON_PRO_PASS"),
      token: opts["pro-token"] ?? env("DARKMOON_PRO_TOKEN"),
      refuseInsecureDefault: opts["allow-insecure-default"] ? false : true,
      timeoutMs: opts.timeout ? Number(opts.timeout) * 1e3 : void 0
    };
  }
  if (ossData) {
    cfg.oss = {
      dataDir: ossData,
      reportsDir: opts["oss-reports-dir"] ?? env("DARKMOON_OSS_REPORTS_DIR"),
      scriptPath: opts["oss-script"] ?? env("DARKMOON_OSS_SCRIPT")
    };
  }
  return cfg;
}
function out(json, human, obj) {
  if (json) process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
  else process.stdout.write(human + "\n");
}
function launchInputFrom(opts) {
  const csv = (v) => typeof v === "string" && v.length ? v.split(",").map((s) => s.trim()) : void 0;
  return {
    target: String(opts.target),
    program: opts.program,
    focus: csv(opts.focus),
    severity: opts.severity,
    outOfScope: csv(opts["out-of-scope"]),
    exclude: csv(opts.exclude)
  };
}
var HELP = `darkmoon-ci \u2014 Darkmoon CI client (contract v${CONTRACT_VERSION})

Usage: darkmoon-ci <command> [options]

Commands:
  detect                         Print the detected backend + capabilities
  launch  --target <t>           Launch a campaign; prints a correlation handle
  status  <campaignId>           Print a campaign's normalized status
  summary <campaignId>           Print the severity summary
  findings <campaignId>          List findings (redaction-safe)
  report  <campaignId>           Fetch the report (redacted unless --full --private)
  wait    <campaignId>           Poll until terminal; apply --fail-on exit code
  run     --target <t>           launch + wait + summary + fail-policy (CI one-shot)

Backend options:
  --mode auto|oss|pro            (env DARKMOON_MODE)
  --pro-url <url>                (env DARKMOON_PRO_URL)
  --pro-user / --pro-pass        (env DARKMOON_PRO_USER / DARKMOON_PRO_PASS)
  --pro-token <jwt>              (env DARKMOON_PRO_TOKEN)
  --oss-data-dir <dir>          (env DARKMOON_OSS_DATA_DIR)
  --oss-reports-dir <dir>       (env DARKMOON_OSS_REPORTS_DIR)
  --oss-script <path>           (env DARKMOON_OSS_SCRIPT)

Common options:
  --json                         Machine-readable output
  --fail-on critical,high        Severities that fail the build (default critical,high)
  --timeout <seconds>            Hard timeout for wait/run (default 3600)
  --poll <seconds>               Poll interval (default 5)
  --full --private               (report) emit the UN-redacted report \u2014 internal only
  --out <file>                   (report) write to a file instead of stdout
  --allow-insecure-default       Do not refuse when Pro admin has default password
  --verbose                      Debug logging (still secret-scrubbed)
  -h, --help                     This help

Exit codes: 0 pass \xB7 2 fail-policy tripped \xB7 1 tool/usage error
`;
async function main(argv) {
  const { values, positionals } = (0, import_node_util.parseArgs)({
    args: argv,
    allowPositionals: true,
    options: {
      mode: { type: "string" },
      "pro-url": { type: "string" },
      "pro-user": { type: "string" },
      "pro-pass": { type: "string" },
      "pro-token": { type: "string" },
      "oss-data-dir": { type: "string" },
      "oss-reports-dir": { type: "string" },
      "oss-script": { type: "string" },
      target: { type: "string" },
      program: { type: "string" },
      focus: { type: "string" },
      severity: { type: "string" },
      "out-of-scope": { type: "string" },
      exclude: { type: "string" },
      "fail-on": { type: "string" },
      timeout: { type: "string" },
      poll: { type: "string" },
      json: { type: "boolean", default: false },
      full: { type: "boolean", default: false },
      private: { type: "boolean", default: false },
      out: { type: "string" },
      "allow-insecure-default": { type: "boolean", default: false },
      verbose: { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false }
    }
  });
  const cmd = positionals[0];
  const json = Boolean(values.json);
  if (values.help || !cmd) {
    process.stdout.write(HELP);
    return values.help ? EXIT_OK : EXIT_ERROR;
  }
  const client = new DarkmoonClient(buildConfig(values));
  const ref = positionals[1];
  const timeoutMs = values.timeout ? Number(values.timeout) * 1e3 : void 0;
  const pollIntervalMs = values.poll ? Number(values.poll) * 1e3 : void 0;
  switch (cmd) {
    case "detect": {
      const caps = await client.detect();
      out(json, `edition=${caps.edition} version=${caps.version} available=${caps.available}
features: ${Object.entries(caps.features).filter(([, v]) => v).map(([k]) => k).join(", ") || "none"}` + (caps.warnings.length ? `
warnings:
 - ${caps.warnings.map(scrubSecrets).join("\n - ")}` : ""), caps);
      return EXIT_OK;
    }
    case "launch": {
      if (!values.target) throw usage("launch requires --target");
      const res = await client.launchCampaign(launchInputFrom(values));
      out(json, `launched: runId=${res.runId ?? "-"} nonce=${res.correlation.nonce ?? "-"} (correlation deferred)`, res);
      return EXIT_OK;
    }
    case "status": {
      if (!ref) throw usage("status requires a <campaignId>");
      const c = await client.getCampaignStatus(ref);
      out(json, `campaign ${c.id}: status=${c.status} risk=${c.overallRisk} findings=${c.severity.total}`, stripRaw(c));
      return EXIT_OK;
    }
    case "summary": {
      if (!ref) throw usage("summary requires a <campaignId>");
      const s = await client.getSeveritySummary(ref);
      out(json, `critical=${s.critical} high=${s.high} medium=${s.medium} low=${s.low} info=${s.info} total=${s.total}`, s);
      return EXIT_OK;
    }
    case "findings": {
      if (!ref) throw usage("findings requires a <campaignId>");
      const findings = await client.listFindings({ campaignId: ref, severity: values.severity });
      out(
        json,
        findings.map((f) => `[${f.severity}] ${f.title ?? f.id} (${f.status})`).join("\n") || "(no findings)",
        findings.map(stripRaw)
      );
      return EXIT_OK;
    }
    case "report": {
      if (!ref) throw usage("report requires a <campaignId>");
      const rep = await client.getReport(ref, { full: Boolean(values.full), private: Boolean(values.private) });
      if (values.out) {
        await import_node_fs3.promises.writeFile(String(values.out), rep.content, "utf8");
        out(json, `report written to ${values.out} (redacted=${rep.redacted})`, { file: values.out, redacted: rep.redacted });
      } else {
        out(json, rep.content, rep);
      }
      return EXIT_OK;
    }
    case "wait": {
      if (!ref) throw usage("wait requires a <campaignId>");
      const c = await client.waitForCompletion(ref, { timeoutMs, pollIntervalMs, onProgress: (p) => values.verbose && process.stderr.write(`[status] ${p.status}
`) });
      const findings = await client.listFindings({ campaignId: c.id });
      assertCompleted(c.status);
      return emitVerdict(findings, values, json, c.id);
    }
    case "run": {
      if (!values.target) throw usage("run requires --target");
      const launched = await client.launchCampaign(launchInputFrom(values));
      process.stderr.write(`[darkmoon-ci] launched (nonce=${launched.correlation.nonce}); waiting...
`);
      const c = await client.waitForCompletion(launched, { timeoutMs, pollIntervalMs, onProgress: (p) => process.stderr.write(`[status] ${p.status}
`) });
      const findings = await client.listFindings({ campaignId: c.id });
      assertCompleted(c.status);
      return emitVerdict(findings, values, json, c.id);
    }
    default:
      process.stderr.write(`Unknown command: ${cmd}

${HELP}`);
      return EXIT_ERROR;
  }
}
function assertCompleted(status) {
  if (status !== "completed") throw new DarkmoonError("BAD_REQUEST", `Assessment ended with status '${status}'; no findings verdict is available.`);
}
function emitVerdict(findings, values, json, campaignId) {
  const verdict = computeFailPolicy(findings, parseFailOn(values["fail-on"]));
  const payload = {
    campaignId,
    verdict: verdict.failed ? "fail" : "pass",
    failOn: verdict.failOn,
    offending: verdict.offending,
    total: findings.length,
    reason: verdict.reason
  };
  out(json, `${verdict.failed ? "FAIL" : "PASS"} \u2014 ${verdict.reason}`, payload);
  return verdict.failed ? EXIT_POLICY : EXIT_OK;
}
function stripRaw(o) {
  const { raw: _raw, ...rest } = o;
  return rest;
}
function usage(msg) {
  return new DarkmoonError("BAD_REQUEST", msg);
}
main(process.argv.slice(2)).then((code) => process.exit(code)).catch((err) => {
  const msg = err instanceof DarkmoonError ? `${err.code}: ${err.message}` : String(err?.message ?? err);
  process.stderr.write(`[darkmoon-ci] error: ${scrubSecrets(msg)}
`);
  process.exit(EXIT_ERROR);
});
