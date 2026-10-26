import * as core from '@actions/core';
import type { DarkmoonClientConfig, LaunchInput } from '@darkmoon/client';

export type Mode = 'auto' | 'oss' | 'pro';
export type ReportFormat = 'markdown' | 'json' | 'sarif';

export interface ActionInputs {
  mode: Mode;
  clientConfig: DarkmoonClientConfig;
  launch: LaunchInput;
  /** When set, attach to this existing campaign instead of launching a new one. */
  attachCampaignId?: string;
  /** Raw fail-on string (e.g. "critical,high"); client parses/validates it. */
  failOn: string;
  /** When false (default), nothing is posted to shared surfaces. */
  postReport: boolean;
  /** When true, fetch the UN-redacted report to the private artifact (two-key opt-in). */
  fullReport: boolean;
  reportFormat: ReportFormat;
  reportDir: string;
  githubToken?: string;
  pollIntervalMs: number;
  timeoutMs: number;
  /** Kept for masking. */
  secretsToMask: string[];
}

const VALID_REPORT_FORMATS: ReportFormat[] = ['markdown', 'json', 'sarif'];

function csv(name: string): string[] {
  const raw = core.getInput(name);
  if (!raw) return [];
  return raw
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function optional(name: string): string | undefined {
  const v = core.getInput(name);
  return v ? v : undefined;
}

function boolInput(name: string): boolean {
  try {
    return core.getBooleanInput(name);
  } catch {
    return false;
  }
}

function parseMode(): Mode {
  const m = (core.getInput('mode') || 'auto').toLowerCase();
  if (m === 'auto' || m === 'oss' || m === 'pro') return m;
  core.warning(`Unknown mode '${m}', falling back to 'auto'.`);
  return 'auto';
}

function parseReportFormat(): ReportFormat {
  const f = (core.getInput('report-format') || 'markdown').toLowerCase();
  if ((VALID_REPORT_FORMATS as string[]).includes(f)) return f as ReportFormat;
  core.warning(`Unknown report-format '${f}', falling back to 'markdown'.`);
  return 'markdown';
}

export function readInputs(): ActionInputs {
  const mode = parseMode();

  const baseUrl = optional('base-url');
  const apiToken = optional('api-token');
  const username = optional('username');
  const password = optional('password');

  const ossDataDir = optional('oss-data-dir');
  const ossReportsDir = optional('oss-reports-dir');
  const ossScriptPath = optional('oss-script-path');
  const ossLaunchTemplate = csv('oss-launch-template');

  // Validate transport availability against mode.
  if (mode === 'pro' && !baseUrl) {
    throw new Error("mode=pro requires 'base-url'.");
  }
  if (mode === 'oss' && !ossDataDir) {
    throw new Error("mode=oss requires 'oss-data-dir' (host path with campaigns/ + vulnerabilities/).");
  }
  if (mode === 'auto' && !baseUrl && !ossDataDir) {
    throw new Error("mode=auto requires either 'base-url' (Pro) or 'oss-data-dir' (OSS).");
  }

  const clientConfig: DarkmoonClientConfig = { mode };
  if (baseUrl) {
    clientConfig.pro = {
      baseUrl,
      token: apiToken,
      username,
      password,
      timeoutMs: Number(core.getInput('pro-timeout-ms') || '15000') || 15000,
      // Default true: refuse to run against a Pro admin still on the default password.
      refuseInsecureDefault: core.getInput('refuse-insecure-default') === 'false' ? false : true,
    };
  }
  if (ossDataDir) {
    clientConfig.oss = {
      dataDir: ossDataDir,
      reportsDir: ossReportsDir,
      scriptPath: ossScriptPath,
      launchTemplate: ossLaunchTemplate.length ? ossLaunchTemplate : undefined,
    };
  }

  const attachCampaignId = optional('campaign-id');

  const target = core.getInput('target');
  const targets = csv('targets');
  if (!attachCampaignId && !target && targets.length === 0) {
    throw new Error(
      "No target provided. Set 'target'/'targets', or 'campaign-id' to attach to an existing campaign."
    );
  }

  const launch: LaunchInput = {
    target: target || targets[0] || '',
    program: optional('program'),
    targets: targets.length > 1 ? targets : undefined,
    outOfScope: csv('out-of-scope').length ? csv('out-of-scope') : undefined,
    exclude: csv('exclude').length ? csv('exclude') : undefined,
    focus: csv('focus').length ? csv('focus') : undefined,
    noise: optional('noise'),
    severity: optional('severity'),
    format: optional('format'),
    rules: optional('rules') ? optional('rules')!.split(';').map((s) => s.trim()).filter(Boolean) : undefined,
    safeHarbor: boolInput('safe-harbor') ? 'yes' : undefined,
  };

  const pollIntervalMs = Number(core.getInput('poll-interval-ms') || '5000');
  const timeoutMs = Number(core.getInput('timeout-ms') || String(2 * 60 * 60 * 1000));

  const secretsToMask = [apiToken, password, core.getInput('github-token')].filter(
    (v): v is string => !!v && v.length >= 4
  );

  return {
    mode,
    clientConfig,
    launch,
    attachCampaignId,
    failOn: core.getInput('fail-on') || '',
    postReport: boolInput('post-report'),
    fullReport: boolInput('full-report'),
    reportFormat: parseReportFormat(),
    reportDir: core.getInput('report-dir') || process.env.RUNNER_TEMP || '.',
    githubToken: optional('github-token'),
    pollIntervalMs: Number.isFinite(pollIntervalMs) ? pollIntervalMs : 5000,
    timeoutMs: Number.isFinite(timeoutMs) ? timeoutMs : 2 * 60 * 60 * 1000,
    secretsToMask,
  };
}
