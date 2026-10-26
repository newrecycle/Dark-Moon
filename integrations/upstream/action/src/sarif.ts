import type { Finding, Severity } from '@darkmoon/client';
import { redact } from './redact.js';

// The real Finding uses cvssScore?: number | null; treat null as absent.

/**
 * GitHub-platform adapter: synthesize a SARIF 2.1.0 log from Darkmoon findings.
 *
 * Darkmoon's OSS engine and Pro REST API do NOT emit SARIF natively (confirmed
 * against the source: reports are Markdown, findings are JSON). GitHub code
 * scanning consumes SARIF, so this action maps findings → SARIF locally. This is
 * a presentation/format adapter for the GitHub platform, not a reimplementation
 * of the Darkmoon client. Output is written to a private runner file; the user
 * feeds it to github/codeql-action/upload-sarif themselves.
 */

function sarifLevel(severity: Severity): 'error' | 'warning' | 'note' {
  switch (severity) {
    case 'critical':
    case 'high':
      return 'error';
    case 'medium':
      return 'warning';
    default:
      return 'note';
  }
}

function securitySeverity(severity: Severity, cvss?: number): string {
  if (typeof cvss === 'number' && cvss >= 0 && cvss <= 10) {
    return cvss.toFixed(1);
  }
  // GitHub security-severity buckets (0-10) when no CVSS is available.
  switch (severity) {
    case 'critical':
      return '9.5';
    case 'high':
      return '8.0';
    case 'medium':
      return '5.5';
    case 'low':
      return '3.0';
    default:
      return '1.0';
  }
}

function ruleIdFor(f: Finding): string {
  const base = (f.category || 'finding').toString().toLowerCase();
  return `darkmoon/${base.replace(/[^a-z0-9._-]+/g, '-')}`;
}

/**
 * Strip contract-forbidden fields before a finding is serialized to a CI
 * artifact: `raw` (may carry rehydrated real values) and `evidence` (forced null).
 */
export function redactFindingForArtifact(f: Finding): Omit<Finding, 'raw'> {
  const { raw: _raw, ...rest } = f as Finding & { raw?: unknown };
  return { ...rest, evidence: null };
}

export interface SarifOptions {
  toolVersion?: string;
  informationUri?: string;
}

export function buildSarif(findings: Finding[], opts: SarifOptions = {}): string {
  const rulesById = new Map<string, Record<string, unknown>>();

  const results = findings.map((f) => {
    const ruleId = ruleIdFor(f);
    if (!rulesById.has(ruleId)) {
      rulesById.set(ruleId, {
        id: ruleId,
        name: (f.category || 'Finding').toString(),
        shortDescription: { text: redact(f.title || ruleId) },
        defaultConfiguration: { level: sarifLevel(f.severity) },
        properties: {
          tags: ['security', 'darkmoon', `severity:${f.severity}`],
          'security-severity': securitySeverity(f.severity, f.cvssScore ?? undefined),
        },
      });
    }

    // Location: Darkmoon findings target running endpoints, not source files.
    // Anchor to a synthetic path so code scanning still ingests the alert.
    const endpoint = f.endpoint ? redact(f.endpoint) : '';
    const artifactUri = endpoint
      ? `darkmoon/${endpoint.replace(/^https?:\/\//i, '').replace(/[^a-zA-Z0-9._/-]+/g, '_')}`
      : `darkmoon/finding/${f.id}`;

    const messageParts = [redact(f.title || 'Finding')];
    messageParts.push(`[status: ${f.status}]`);
    if (endpoint) messageParts.push(`endpoint: ${endpoint}`);

    return {
      ruleId,
      level: sarifLevel(f.severity),
      message: { text: messageParts.join(' ') },
      locations: [
        {
          physicalLocation: {
            artifactLocation: { uri: artifactUri },
            region: { startLine: 1 },
          },
        },
      ],
      properties: {
        severity: f.severity,
        status: f.status,
        cvss: typeof f.cvssScore === 'number' ? f.cvssScore : null,
        darkmoonFindingId: f.id,
      },
    };
  });

  const sarif = {
    $schema:
      'https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json',
    version: '2.1.0',
    runs: [
      {
        tool: {
          driver: {
            name: 'Darkmoon',
            informationUri: opts.informationUri || 'https://dark-moon.org',
            version: opts.toolVersion || '1.0.0',
            rules: Array.from(rulesById.values()),
          },
        },
        results,
      },
    ],
  };

  return JSON.stringify(sarif, null, 2);
}
