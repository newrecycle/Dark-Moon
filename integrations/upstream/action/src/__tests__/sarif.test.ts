import { buildSarif, redactFindingForArtifact } from '../sarif.js';
import { registerSecret, _clearSecrets } from '../redact.js';
import type { Finding } from '@darkmoon/client';

const finding = (over: Partial<Finding> = {}): Finding => ({
  id: 'vuln_abc123',
  campaignId: 'camp_1',
  projectId: 'proj_1',
  targetId: 'tgt_1',
  title: 'SQL Injection in login',
  severity: 'critical',
  status: 'exploited',
  category: 'sql_injection',
  cve: null,
  cvssScore: 9.8,
  cvssVector: null,
  mitreAttackId: null,
  mitreAttackName: null,
  endpoint: '/api/login',
  description: null,
  remediation: null,
  discoveredByAgent: 'nodejs',
  discoveredAt: null,
  evidence: null,
  edition: 'oss',
  ...over,
});

describe('buildSarif', () => {
  beforeEach(() => _clearSecrets());

  it('produces valid SARIF 2.1.0 structure', () => {
    const sarif = JSON.parse(buildSarif([finding()]));
    expect(sarif.version).toBe('2.1.0');
    expect(sarif.runs[0].tool.driver.name).toBe('Darkmoon');
    expect(sarif.runs[0].results).toHaveLength(1);
    const res = sarif.runs[0].results[0];
    expect(res.level).toBe('error');
    expect(res.ruleId).toBe('darkmoon/sql_injection');
    expect(res.properties.severity).toBe('critical');
  });

  it('maps severities to SARIF levels and security-severity', () => {
    const sarif = JSON.parse(
      buildSarif([
        finding({ id: 'v1', severity: 'critical', cvssScore: undefined, category: 'a' }),
        finding({ id: 'v2', severity: 'medium', cvssScore: undefined, category: 'b' }),
        finding({ id: 'v3', severity: 'low', cvssScore: undefined, category: 'c' }),
      ])
    );
    const levels = sarif.runs[0].results.map((r: any) => r.level);
    expect(levels).toEqual(['error', 'warning', 'note']);
    const rules = sarif.runs[0].tool.driver.rules;
    const critRule = rules.find((r: any) => r.id === 'darkmoon/a');
    expect(critRule.properties['security-severity']).toBe('9.5');
  });

  it('redacts secrets that leak into titles/endpoints', () => {
    registerSecret('secret-host-value-xyz');
    const sarif = buildSarif([
      finding({ title: 'leak secret-host-value-xyz', endpoint: 'http://secret-host-value-xyz/x' }),
    ]);
    expect(sarif).not.toContain('secret-host-value-xyz');
  });

  it('redactFindingForArtifact strips raw and nulls evidence', () => {
    const f = finding({
      evidence: { commands: ['secret cmd'] } as any,
      raw: { rehydrated: 'REAL-HOST-10.0.0.5', internal: true },
    } as Partial<Finding>);
    const out = redactFindingForArtifact(f);
    expect('raw' in out).toBe(false);
    expect(out.evidence).toBeNull();
    const serialized = JSON.stringify(out);
    expect(serialized).not.toContain('REAL-HOST-10.0.0.5');
    // keeps the safe fields
    expect(out.severity).toBe('critical');
    expect(out.id).toBe('vuln_abc123');
  });

  it('buildSarif never emits a raw field', () => {
    const sarif = buildSarif([
      finding({ raw: { leak: 'DO-NOT-EMIT-RAW' } } as Partial<Finding>),
    ]);
    expect(sarif).not.toContain('DO-NOT-EMIT-RAW');
    expect(sarif).not.toContain('"raw"');
  });

  it('handles findings without endpoint or cvss', () => {
    const sarif = JSON.parse(
      buildSarif([finding({ endpoint: undefined, cvssScore: undefined })])
    );
    const res = sarif.runs[0].results[0];
    expect(res.locations[0].physicalLocation.artifactLocation.uri).toContain(
      'darkmoon/finding/'
    );
  });
});
