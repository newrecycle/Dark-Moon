/**
 * Adapter: real `@darkmoon/client` (the DarkmoonClient facade, plan §2.2) →
 * the extension's stable `DarkmoonClient` interface (contract.ts).
 *
 * The extension is written against contract.ts so its UI never has to track the
 * (richer) package surface. This file is the single translation layer; it does
 * NOT reimplement any backend logic — it delegates every call to the package.
 *
 * The package is required dynamically (it is an optional dependency): a missing
 * package degrades gracefully in clientLoader instead of breaking activation.
 */
import type {
  Campaign,
  Capabilities,
  ClientConfig,
  DarkmoonClient,
  Evidence,
  Finding,
  LaunchOptions,
  LaunchResult,
  ReportContent,
  ReportMeta,
  Severity,
} from './contract';

// Loose shapes of the package surface we touch (kept local so typecheck passes
// without the package installed).
interface PkgSeveritySummary {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
  total: number;
}
interface PkgCampaign {
  id: string;
  projectId: string | null;
  targetId: string | null;
  sessionId: string | null;
  target: string | null;
  status: string;
  overallRisk: string;
  createdAt: string | null;
  durationSeconds: number | null;
  reportPath: string | null;
  isSubagent: boolean;
  severity: PkgSeveritySummary;
  executiveSummary: string | null;
  edition: 'oss' | 'pro';
}
interface PkgEvidence {
  commands: string[];
  payloads: string[];
  rawRequest: string | null;
  rawResponse: string | null;
  extractedData: string | null;
  logs: string[];
  explanation: string | null;
  redacted: boolean;
}
interface PkgFinding {
  id: string;
  campaignId: string | null;
  projectId: string | null;
  targetId: string | null;
  title: string | null;
  severity: Severity;
  status: string;
  category: string | null;
  cve: string | null;
  cvssScore: number | null;
  cvssVector: string | null;
  mitreAttackId: string | null;
  mitreAttackName: string | null;
  endpoint: string | null;
  description: string | null;
  remediation: string | null;
  discoveredByAgent: string | null;
  discoveredAt: string | null;
  evidence: PkgEvidence | null;
}
interface PkgReport {
  campaignId: string;
  format: string;
  content: string;
  ready: boolean;
  redacted: boolean;
}
interface PkgCapabilities {
  edition: 'oss' | 'pro';
  features: {
    restApi: boolean;
    streaming: boolean;
    auth: boolean;
    remediation: boolean;
    dashboard: boolean;
    scheduler: boolean;
  };
  warnings: string[];
}
interface PkgClient {
  detect(): Promise<PkgCapabilities>;
  listCampaigns(filter?: { status?: string; targetId?: string }): Promise<PkgCampaign[]>;
  getCampaign(id: string): Promise<PkgCampaign>;
  listFindings(
    filter: { campaignId?: string },
    opts?: { includeEvidence?: boolean; full?: boolean; private?: boolean }
  ): Promise<PkgFinding[]>;
  getFinding(
    id: string,
    opts?: { includeEvidence?: boolean; full?: boolean; private?: boolean }
  ): Promise<PkgFinding>;
  getReport(
    campaign: string,
    opts?: { full?: boolean; private?: boolean }
  ): Promise<PkgReport>;
  launchCampaign(input: Record<string, unknown>): Promise<{
    campaignId: string | null;
    runId: string | null;
    correlation?: { campaignId: string | null; runId: string | null };
  }>;
}
type PkgCtor = new (cfg: Record<string, unknown>) => PkgClient;

function toStats(s: PkgSeveritySummary): Campaign['stats'] {
  return {
    total_findings: s.total,
    critical: s.critical,
    high: s.high,
    medium: s.medium,
    low: s.low,
    info: s.info,
  };
}

function mapCampaign(c: PkgCampaign): Campaign {
  return {
    id: c.id,
    project_id: c.projectId ?? undefined,
    target_id: c.targetId ?? undefined,
    session_id: c.sessionId ?? undefined,
    is_subagent: c.isSubagent,
    date: c.createdAt ?? undefined,
    duration_seconds: c.durationSeconds ?? undefined,
    status: c.status,
    overall_risk: c.overallRisk,
    stats: toStats(c.severity),
    report_path: c.reportPath ?? undefined,
    executive_summary: c.executiveSummary ?? undefined,
    target: c.target ?? undefined,
  };
}

function mapEvidence(e: PkgEvidence | null): Evidence | undefined {
  if (!e) {
    return undefined;
  }
  return {
    commands: e.commands,
    payloads: e.payloads,
    raw_request: e.rawRequest ?? undefined,
    raw_response: e.rawResponse ?? undefined,
    extracted_data: e.extractedData ?? undefined,
    logs: e.logs,
    explanation: e.explanation ?? undefined,
  };
}

function mapFinding(f: PkgFinding): Finding {
  return {
    id: f.id,
    campaign_id: f.campaignId ?? '',
    title: f.title ?? '(untitled)',
    severity: f.severity,
    status: f.status,
    category: f.category ?? undefined,
    cve: f.cve,
    cvss_score: f.cvssScore,
    cvss_vector: f.cvssVector,
    mitre_attack_id: f.mitreAttackId,
    mitre_attack_name: f.mitreAttackName,
    endpoint: f.endpoint ?? undefined,
    plugin_or_component: f.endpoint ?? undefined,
    description: f.description ?? '',
    remediation: f.remediation ?? undefined,
    discovered_by_agent: f.discoveredByAgent ?? undefined,
    discovered_at: f.discoveredAt ?? undefined,
    project_id: f.projectId ?? undefined,
    target_id: f.targetId ?? undefined,
    evidence: mapEvidence(f.evidence),
  };
}

function mapCapabilities(c: PkgCapabilities): Capabilities {
  return {
    edition: c.edition,
    launchCampaign: true,
    liveStatus: c.features.streaming,
    rehydratedReports: true,
    webDashboard: c.features.dashboard,
  };
}

class RealClientAdapter implements DarkmoonClient {
  private campaignCache: PkgCampaign[] | undefined;

  constructor(private readonly pkg: PkgClient) {}

  async capabilities(): Promise<Capabilities> {
    return mapCapabilities(await this.pkg.detect());
  }

  private async campaigns(): Promise<PkgCampaign[]> {
    if (!this.campaignCache) {
      this.campaignCache = await this.pkg.listCampaigns();
    }
    return this.campaignCache;
  }

  async listCampaigns(): Promise<Campaign[]> {
    this.campaignCache = await this.pkg.listCampaigns();
    return this.campaignCache.map(mapCampaign);
  }

  async getCampaign(id: string): Promise<Campaign> {
    return mapCampaign(await this.pkg.getCampaign(id));
  }

  async listFindings(campaignId?: string): Promise<Finding[]> {
    if (campaignId) {
      const f = await this.pkg.listFindings(
        { campaignId },
        { includeEvidence: true }
      );
      return f.map(mapFinding);
    }
    // No cross-campaign list in the contract: aggregate per campaign.
    const camps = await this.campaigns();
    const all: Finding[] = [];
    for (const c of camps) {
      const f = await this.pkg.listFindings(
        { campaignId: c.id },
        { includeEvidence: true }
      );
      all.push(...f.map(mapFinding));
    }
    return all;
  }

  async getFinding(id: string): Promise<Finding | undefined> {
    try {
      return mapFinding(await this.pkg.getFinding(id, { includeEvidence: true }));
    } catch {
      return undefined;
    }
  }

  async listReports(): Promise<ReportMeta[]> {
    const camps = await this.listCampaigns();
    return camps
      .filter((c) => !!c.report_path)
      .map((c) => ({
        id: c.id,
        campaignId: c.id,
        title: c.target ? `Report — ${c.target}` : `Report ${c.id}`,
        target: c.target,
        generatedAt: c.date,
        path: c.report_path,
      }));
  }

  async getReport(
    id: string,
    opts?: { rehydrate?: boolean }
  ): Promise<ReportContent> {
    const rehydrate = opts?.rehydrate === true;
    // Two-key opt-in required by the package for the full body.
    const r = rehydrate
      ? await this.pkg.getReport(id, { full: true, private: true })
      : await this.pkg.getReport(id);
    if (!r.ready) {
      return { markdown: '# Report not ready\n\nThis campaign has no finalized report yet.', rehydrated: false };
    }
    return { markdown: r.content, rehydrated: !r.redacted };
  }

  async launchCampaign(o: LaunchOptions): Promise<LaunchResult> {
    const input: Record<string, unknown> = { target: o.target };
    if (o.focus) {
      input.focus = o.focus.split(',').map((s) => s.trim()).filter(Boolean);
    }
    if (o.noise) {
      input.noise = o.noise;
    }
    if (o.severityCap) {
      input.severity = o.severityCap;
    }
    if (o.creds) {
      input.credentials = [o.creds];
    }
    if (o.token) {
      input.tokens = [o.token];
    }
    const res = await this.pkg.launchCampaign(input);
    const campaignId =
      res.campaignId ?? res.correlation?.campaignId ?? res.runId ?? 'pending';
    return { campaignId, status: 'queued' };
  }
}

/** Build the real client from ClientConfig and wrap it in the adapter. */
export function createRealClient(cfg: ClientConfig): DarkmoonClient {
  // Dynamic require so a missing optional dependency never breaks activation.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const mod = require('@darkmoon/client') as { DarkmoonClient: PkgCtor };
  const Ctor = mod.DarkmoonClient;

  const pkgCfg: Record<string, unknown> = { mode: cfg.mode };
  if (cfg.baseUrl) {
    pkgCfg.pro = { baseUrl: cfg.baseUrl, token: cfg.token };
  }
  if (cfg.dataDir) {
    // Documented OSS layout: campaigns/ + vulnerabilities/ + reports/ under dataDir.
    pkgCfg.oss = {
      dataDir: cfg.dataDir,
      reportsDir: `${cfg.dataDir.replace(/\/+$/, '')}/reports`,
      ...(cfg.cliPath ? { scriptPath: cfg.cliPath } : {}),
    };
  }
  return new RealClientAdapter(new Ctor(pkgCfg));
}
