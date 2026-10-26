import * as core from '@actions/core';
import type { SummaryTableRow } from '@actions/core/lib/summary.js';
import type {
  Campaign,
  Capabilities,
  FailPolicyResult,
  FindingStatus,
} from '@darkmoon/client';

const SEV_EMOJI: Record<string, string> = {
  critical: '🟥',
  high: '🟧',
  medium: '🟨',
  low: '🟦',
  info: '⬜',
};

export type StatusCounts = Record<FindingStatus, number>;

/**
 * Write a redaction-safe severity table to $GITHUB_STEP_SUMMARY.
 * Only aggregate counts + campaign metadata — never finding evidence, endpoints,
 * payloads, tokens, or the report body.
 */
export async function writeStepSummary(
  campaign: Campaign,
  statusCounts: StatusCounts,
  caps: Capabilities,
  policy: FailPolicyResult,
  reportPath: string | undefined
): Promise<void> {
  const s = campaign.severity;
  const sevTable: SummaryTableRow[] = [
    [
      { data: 'Severity', header: true },
      { data: 'Count', header: true },
    ],
    ...(['critical', 'high', 'medium', 'low', 'info'] as const).map((k) => [
      `${SEV_EMOJI[k]} ${k[0].toUpperCase()}${k.slice(1)}`,
      String(s[k]),
    ]),
    ['**Total**', `**${s.total}**`],
  ];

  const statusTable: SummaryTableRow[] = [
    [
      { data: 'Status', header: true },
      { data: 'Count', header: true },
    ],
    ['Exploited', String(statusCounts.exploited)],
    ['Confirmed', String(statusCounts.confirmed)],
    ['Unconfirmed', String(statusCounts.unconfirmed)],
    ['Remediated', String(statusCounts.remediated)],
  ];

  core.summary
    .addHeading('Darkmoon Assessment', 2)
    .addRaw(
      [
        `**Edition:** ${caps.edition.toUpperCase()}`,
        `**Campaign:** \`${campaign.id}\``,
        `**Status:** ${campaign.status}`,
        `**Overall risk:** ${campaign.overallRisk}`,
      ].join(' · '),
      true
    )
    .addHeading('Findings by severity', 3)
    .addTable(sevTable)
    .addHeading('Findings by status', 3)
    .addTable(statusTable);

  for (const w of caps.warnings || []) {
    core.summary.addRaw(`\n> ⚠️ ${w}\n`, true);
  }

  core.summary.addRaw(
    policy.failed ? `\n> ❌ ${policy.reason}\n` : `\n> ✅ ${policy.reason}\n`,
    true
  );

  if (reportPath) {
    core.summary.addRaw(
      `\n_Report written to a private runner artifact: \`${reportPath}\`._\n`,
      true
    );
  }

  await core.summary.write();
}

/** Redaction-safe body for a shared surface (PR/commit comment): counts + links only. */
export function buildSharedSummaryComment(
  campaign: Campaign,
  statusCounts: StatusCounts,
  caps: Capabilities,
  policy: FailPolicyResult
): string {
  const s = campaign.severity;
  const line = (['critical', 'high', 'medium', 'low', 'info'] as const)
    .map((k) => `${SEV_EMOJI[k]} ${s[k]} ${k}`)
    .join(' · ');
  return [
    '### Darkmoon assessment summary',
    '',
    `**Edition:** ${caps.edition.toUpperCase()} · **Overall risk:** ${campaign.overallRisk} · **Total findings:** ${s.total}`,
    '',
    line,
    '',
    `Status: ${statusCounts.exploited} exploited · ${statusCounts.confirmed} confirmed · ${statusCounts.unconfirmed} unconfirmed · ${statusCounts.remediated} remediated`,
    '',
    policy.failed ? `❌ ${policy.reason}` : `✅ ${policy.reason}`,
    '',
    '_Only aggregate counts are shared here. The full evidence report is kept private (opt-in via `post-report` / `full-report`)._',
  ].join('\n');
}
