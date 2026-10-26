/**
 * Frozen Darkmoon client contract (plan §2.2).
 *
 * This is a LOCAL TYPE DECLARATION of the surface the extension consumes from
 * the `@darkmoon/client` package (built in parallel). The extension is written
 * exclusively against these types so that:
 *   - it compiles and is fully testable without the real package present, and
 *   - the real `@darkmoon/client` can be wired in for E2E with zero code churn
 *     (its `createClient` must be assignable to `CreateClient` below).
 *
 * Shapes are grounded in the real OSS artifacts (campaign JSON, vulns JSON,
 * markdown reports) and the Pro REST fixtures shipped by @darkmoon/client.
 * Nothing here is invented beyond what those artifacts contain.
 */

export type Edition = 'oss' | 'pro';

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

/**
 * Open string unions: the known literals give autocompletion while forward-
 * compat values are still accepted. `AnyString` is `string` intersected with an
 * empty object so the literals are preserved in the union.
 */
// eslint-disable-next-line @typescript-eslint/ban-types
type AnyString = string & {};

/**
 * Canonical finding/campaign statuses from the frozen @darkmoon/client contract
 * (CONTRACT_VERSION 1.0.0). Kept open (AnyString) for additive forward-compat,
 * but every canonical literal is enumerated so the UI can style/filter them.
 */
export type FindingStatus =
  | 'exploited'
  | 'confirmed'
  | 'unconfirmed'
  | 'remediated'
  | AnyString;
export type CampaignStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'stopped'
  | 'failed'
  | 'unknown'
  | AnyString;

/**
 * Capability descriptor. The extension NEVER hardcodes "if pro" in the UI; it
 * reads these flags so degradation (plan §2.4) is driven by the client, and
 * Pro-only affordances are hidden/disabled on OSS.
 *
 * Deliberately absent (plan §4 threat model): NO infrastructure graph, NO
 * automated PR surface. Even when the backend reports remediation capability,
 * the extension does not expose auto-PR actions.
 */
export interface Capabilities {
  edition: Edition;
  /** Can a new campaign be launched from here (OSS: CLI, Pro: REST). */
  launchCampaign: boolean;
  /** Live status polling of running campaigns (Pro). */
  liveStatus: boolean;
  /** Backend can produce rehydrated (un-redacted) reports on explicit request. */
  rehydratedReports: boolean;
  /** Backend exposes a hosted web dashboard (Pro). Informational only. */
  webDashboard: boolean;
}

export interface CampaignStats {
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
  exploited: number;
  confirmed: number;
  unconfirmed: number;
}

export interface DispatchedAgent {
  agent: string;
  findings: number;
  level: number;
  status: string;
}

export interface Campaign {
  id: string;
  project_id?: string;
  target_id?: string;
  session_id?: string;
  is_subagent?: boolean;
  date?: string;
  duration_seconds?: number;
  status: CampaignStatus;
  methodology?: string;
  agents_dispatched?: DispatchedAgent[];
  cascade_depth?: number;
  overall_risk?: Severity | string;
  /** May be `{}` for a not-yet-started/partial campaign (see Pro fixtures). */
  stats: Partial<CampaignStats>;
  report_path?: string;
  executive_summary?: string;
  /** Convenience mirror of the human target (host:port / url) when known. */
  target?: string;
}

export interface Evidence {
  commands?: string[];
  payloads?: string[];
  raw_request?: string;
  raw_response?: string;
  extracted_data?: unknown;
  screenshots?: string[];
  logs?: string[];
  explanation?: string;
}

export interface Finding {
  id: string;
  campaign_id: string;
  node_id?: string;
  title: string;
  severity: Severity;
  cvss_score?: number | null;
  cvss_vector?: string | null;
  cve?: string | null;
  category?: string;
  mitre_attack_id?: string | null;
  mitre_attack_name?: string | null;
  iso27001_control?: string | null;
  status: FindingStatus;
  description: string;
  evidence?: Evidence;
  remediation?: string;
  plugin_or_component?: string;
  endpoint?: string;
  discovered_by_agent?: string;
  discovered_at?: string;
  project_id?: string;
  target_id?: string;
}

export interface ReportMeta {
  id: string;
  campaignId?: string;
  title?: string;
  target?: string;
  generatedAt?: string;
  /** Backend path (OSS: /reports/...). Never rendered as a filesystem link. */
  path?: string;
}

export interface ReportContent {
  markdown: string;
  /** True only when the returned markdown carries rehydrated real values. */
  rehydrated: boolean;
}

export interface LaunchOptions {
  target: string;
  /** FOCUS=... attacks to prioritise. */
  focus?: string;
  /** NOISE=stealth|low|moderate discovery aggressiveness. */
  noise?: 'stealth' | 'low' | 'moderate';
  /** SEVERITY=... global max severity cap. */
  severityCap?: Severity;
  /** CREDS=role:user:pass[@url] test credentials. */
  creds?: string;
  /** TOKEN=type:value[@host] pre-auth token. NEVER logged. */
  token?: string;
}

export interface LaunchResult {
  campaignId: string;
  status: CampaignStatus;
}

/**
 * The single surface the extension depends on. Every method is async and may
 * reject; the extension is responsible for surfacing failures as UI states.
 */
export interface DarkmoonClient {
  capabilities(): Promise<Capabilities>;
  listCampaigns(): Promise<Campaign[]>;
  getCampaign(id: string): Promise<Campaign>;
  listFindings(campaignId?: string): Promise<Finding[]>;
  getFinding(id: string): Promise<Finding | undefined>;
  listReports(): Promise<ReportMeta[]>;
  /**
   * Redaction-safe by default (plan §4). With `{ rehydrate: false }` (default)
   * the returned markdown must not carry real infrastructure values; the full
   * rehydrated report is only returned when `{ rehydrate: true }` is passed,
   * which the extension does ONLY on an explicit, local user action.
   */
  getReport(id: string, opts?: { rehydrate?: boolean }): Promise<ReportContent>;
  launchCampaign(opts: LaunchOptions): Promise<LaunchResult>;
  dispose?(): void | Promise<void>;
}

export interface ClientConfig {
  mode: 'oss' | 'pro' | 'auto';
  /** Pro REST base URL. */
  baseUrl?: string;
  /** Pro bearer token (sourced from SecretStorage; never from settings). */
  token?: string;
  /** License key (sourced from SecretStorage; never from settings). */
  license?: string;
  /** OSS reports/campaigns data directory. */
  dataDir?: string;
  /** OSS CLI entrypoint (e.g. darkmoon.sh / darkmoon). */
  cliPath?: string;
}

/** `@darkmoon/client`'s `createClient` must be assignable to this. */
export type CreateClient = (
  config: ClientConfig
) => Promise<DarkmoonClient> | DarkmoonClient;

export const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};
