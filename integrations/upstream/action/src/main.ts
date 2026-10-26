import * as fs from 'node:fs';
import * as path from 'node:path';
import * as core from '@actions/core';
import * as github from '@actions/github';
import {
  DarkmoonClient,
  Logger,
  computeFailPolicy,
  scrubSecrets,
  severitySummaryFromFindings,
  CONTRACT_VERSION,
} from '@darkmoon/client';
import type {
  Campaign,
  Capabilities,
  DarkmoonError,
  Finding,
  FindingStatus,
} from '@darkmoon/client';
import { readInputs, type ActionInputs, type ReportFormat } from './inputs.js';
import {
  buildSharedSummaryComment,
  writeStepSummary,
  type StatusCounts,
} from './summary.js';
import { redact, registerSecret } from './redact.js';
import { buildSarif, redactFindingForArtifact } from './sarif.js';

const REPORT_EXT: Record<ReportFormat, string> = {
  markdown: 'md',
  json: 'json',
  sarif: 'sarif',
};

/** Combine the client's scrubSecrets with our per-run registered secrets. */
function safe(s: string): string {
  return scrubSecrets(redact(s));
}

function maskSecrets(inputs: ActionInputs): void {
  for (const secret of inputs.secretsToMask) {
    core.setSecret(secret);
    registerSecret(secret);
  }
}

function statusCountsFromFindings(findings: Finding[]): StatusCounts {
  const counts: StatusCounts = {
    exploited: 0,
    confirmed: 0,
    unconfirmed: 0,
    remediated: 0,
  };
  for (const f of findings) {
    const st = f.status as FindingStatus;
    if (st in counts) counts[st] += 1;
  }
  return counts;
}

function writeReportFile(
  content: string,
  format: ReportFormat,
  dir: string,
  campaignId: string
): string {
  fs.mkdirSync(dir, { recursive: true });
  const out = path.join(dir, `darkmoon-${campaignId}.${REPORT_EXT[format]}`);
  fs.writeFileSync(out, content, { encoding: 'utf8' });
  return out;
}

function setOutputs(
  campaign: Campaign,
  statusCounts: StatusCounts,
  caps: Capabilities,
  reportPath: string | undefined,
  policyFailed: boolean
): void {
  const s = campaign.severity;
  core.setOutput('campaign-id', campaign.id);
  core.setOutput('edition', caps.edition);
  core.setOutput('overall-risk', campaign.overallRisk);
  core.setOutput('total-findings', String(s.total));
  core.setOutput('critical', String(s.critical));
  core.setOutput('high', String(s.high));
  core.setOutput('medium', String(s.medium));
  core.setOutput('low', String(s.low));
  core.setOutput('info', String(s.info));
  core.setOutput('exploited', String(statusCounts.exploited));
  core.setOutput('confirmed', String(statusCounts.confirmed));
  core.setOutput('unconfirmed', String(statusCounts.unconfirmed));
  core.setOutput('remediated', String(statusCounts.remediated));
  core.setOutput('report-path', reportPath ?? '');
  core.setOutput('policy-failed', String(policyFailed));
}

async function postSharedSummary(inputs: ActionInputs, body: string): Promise<void> {
  if (!inputs.githubToken) {
    core.warning('post-report is enabled but no github-token was provided; skipping shared comment.');
    return;
  }
  try {
    const octokit = github.getOctokit(inputs.githubToken);
    const { owner, repo } = github.context.repo;
    const pr = github.context.payload.pull_request;
    if (pr && pr.number) {
      await octokit.rest.issues.createComment({ owner, repo, issue_number: pr.number, body });
      core.info(`Posted severity summary to PR #${pr.number}.`);
    } else if (github.context.sha) {
      await octokit.rest.repos.createCommitComment({ owner, repo, commit_sha: github.context.sha, body });
      core.info('Posted severity summary as a commit comment.');
    } else {
      core.warning('No PR or commit context available; skipping shared comment.');
    }
  } catch (err) {
    core.warning(`Could not post shared summary: ${safe(String(err))}`);
  }
}

/** Best-effort report fetch/write. Never fails the job. */
async function fetchReport(
  client: DarkmoonClient,
  campaign: Campaign,
  inputs: ActionInputs,
  findings: Finding[]
): Promise<string | undefined> {
  try {
    if (inputs.reportFormat === 'sarif') {
      // GitHub adapter: synthesize SARIF from (redacted, evidence-free) findings.
      const sarif = buildSarif(findings, { toolVersion: campaign.edition });
      const p = writeReportFile(sarif, 'sarif', inputs.reportDir, campaign.id);
      core.info(`SARIF synthesized from findings (private): ${p}`);
      return p;
    }
    if (inputs.reportFormat === 'json') {
      // Strip the contract-forbidden `raw` field (may carry rehydrated real
      // values) and force evidence to null before serializing to the artifact.
      const safeFindings = findings.map(redactFindingForArtifact);
      const p = writeReportFile(
        JSON.stringify(safeFindings, null, 2),
        'json',
        inputs.reportDir,
        campaign.id
      );
      core.info(`Findings JSON written (private, redacted): ${p}`);
      return p;
    }
    // markdown: redacted by default; full only on explicit two-key opt-in.
    const report = inputs.fullReport
      ? await client.getReport(campaign.id, { full: true, private: true })
      : await client.getReport(campaign.id);
    if (!report.ready) {
      core.warning('Report not ready yet; skipping report artifact.');
      return undefined;
    }
    const p = writeReportFile(report.content, 'markdown', inputs.reportDir, campaign.id);
    core.info(`Report written (private, redacted=${report.redacted}): ${p}`);
    return p;
  } catch (err) {
    core.warning(`Report unavailable: ${safe(String(err))}`);
    return undefined;
  }
}

function isDarkmoonError(err: unknown): err is DarkmoonError {
  return !!err && typeof err === 'object' && 'code' in err;
}

export async function run(): Promise<void> {
  let inputs: ActionInputs;
  try {
    inputs = readInputs();
  } catch (err) {
    core.setFailed(safe(err instanceof Error ? err.message : String(err)));
    return;
  }

  maskSecrets(inputs);
  core.debug(`@darkmoon/client contract ${CONTRACT_VERSION}`);

  // Route the client's (secret-free) log lines into the runner log, defensively
  // scrubbed again on our side. debug lines only surface with ACTIONS_STEP_DEBUG.
  const logger = new Logger(core.isDebug() ? 'debug' : 'info', (line: string) =>
    core.info(safe(line))
  );
  const client = new DarkmoonClient({ ...inputs.clientConfig, logger });

  let caps: Capabilities;
  try {
    caps = await core.group('Detect Darkmoon edition', () => client.detect());
    core.info(
      `Edition: ${caps.edition} · mode: ${caps.mode} · version: ${caps.version} · detectedBy: ${caps.detectedBy}`
    );
    for (const w of caps.warnings || []) core.warning(`Darkmoon: ${w}`);
    if (!caps.available) {
      core.warning('Darkmoon backend not positively confirmed reachable; proceeding best-effort.');
    }
  } catch (err) {
    const code = isDarkmoonError(err) ? ` [${err.code}]` : '';
    core.setFailed(`Edition detection failed${code}: ${safe(String(err))}`);
    return;
  }

  let campaign: Campaign;
  try {
    if (inputs.attachCampaignId) {
      // Attach mode: evaluate an existing campaign; no new assessment is launched.
      campaign = await core.group(`Attach to campaign ${inputs.attachCampaignId}`, () =>
        client.waitForCompletion(inputs.attachCampaignId as string, {
          timeoutMs: inputs.timeoutMs,
          pollIntervalMs: inputs.pollIntervalMs,
          failOnStuck: true,
          onProgress: (c) => core.info(`Status: ${c.status}`),
        })
      );
      core.info(`Attached to existing campaign ${campaign.id} (no assessment launched).`);
    } else {
    const launched = await core.group('Launch assessment', () =>
      client.launchCampaign(inputs.launch)
    );
    core.info('Campaign launched; tracking to completion.');

    campaign = await core.group(
      caps.features.streaming ? 'Track (SSE + wait)' : 'Track (polling)',
      async () => {
        // Live progress events (secret-free) when streaming is available.
        if (caps.features.streaming) {
          try {
            for await (const ev of client.streamProgress(launched)) {
              if (ev.message) core.info(`Progress: ${safe(ev.message)}`);
              if (ev.terminal) break;
            }
          } catch (e) {
            core.debug(`streamProgress ended: ${safe(String(e))}`);
          }
        }
        return client.waitForCompletion(launched, {
          timeoutMs: inputs.timeoutMs,
          pollIntervalMs: inputs.pollIntervalMs,
          failOnStuck: true,
          onProgress: (c) => core.info(`Status: ${c.status}`),
        });
      }
    );
    }
  } catch (err) {
    const code = isDarkmoonError(err) ? ` [${err.code}]` : '';
    core.setFailed(`Assessment failed${code}: ${safe(String(err))}`);
    return;
  }

  // Read findings once (evidence-free) for status counts, report, and a severity
  // fallback. Severity summary carries no status breakdown.
  let findings: Finding[] = [];
  let statusCounts: StatusCounts;
  try {
    findings = await client.listFindings({ campaignId: campaign.id });
    statusCounts = statusCountsFromFindings(findings);
  } catch (err) {
    core.warning(`Could not read findings: ${safe(String(err))}`);
    statusCounts = { exploited: 0, confirmed: 0, unconfirmed: 0, remediated: 0 };
  }

  // Defensive: if the campaign's severity summary is empty but findings exist,
  // recompute it from the findings so the gate/table are never falsely zero.
  if (campaign.severity.total === 0 && findings.length > 0) {
    campaign = { ...campaign, severity: severitySummaryFromFindings(findings) };
  }

  const reportPath = await fetchReport(client, campaign, inputs, findings);

  // Pass/fail computed from FINDINGS (never exit code) via the client helper.
  // Empty fail-on => never fail (pass []); a non-empty string is parsed by the
  // client. NB: passing undefined/"" would default the client to critical,high.
  const failOnArg = inputs.failOn.trim() ? inputs.failOn : [];
  const policy = computeFailPolicy(campaign.severity, failOnArg);

  try {
    await writeStepSummary(campaign, statusCounts, caps, policy, reportPath);
  } catch (err) {
    // A step-summary write hiccup must never mask the findings-based verdict.
    core.warning(`Could not write step summary: ${safe(String(err))}`);
  }
  setOutputs(campaign, statusCounts, caps, reportPath, policy.failed);

  if (inputs.postReport) {
    const body = buildSharedSummaryComment(campaign, statusCounts, caps, policy);
    await postSharedSummary(inputs, body);
  }

  if (policy.failed) {
    core.setFailed(policy.reason);
  } else {
    core.info(policy.reason);
  }
}
