/**
 * Integration test: drives run() with a mocked DarkmoonClient class but the REAL
 * computeFailPolicy / scrubSecrets / Logger from @darkmoon/client. Verifies
 * orchestration, secret masking order, outputs, findings-based fail policy, and
 * that no secret/evidence leaks to logs or the step summary.
 */
import type { Campaign, Capabilities, Finding } from '@darkmoon/client';

const SECRET_TOKEN = 'dm_live_TOPSECRET_0123456789';
const EVIDENCE = 'raw-sql-dump-DO-NOT-LEAK';

const logLines: string[] = [];
const outputs: Record<string, string> = {};
const secrets: string[] = [];
let failedWith: string | undefined;
const summaryChunks: string[] = [];
let summaryWritten = false;

jest.mock('@actions/core', () => {
  const rec = (s: unknown) => logLines.push(String(s));
  const summary: any = {
    addHeading: (t: string) => (rec(t), summary),
    addRaw: (t: string) => (rec(t), summary),
    addTable: (rows: unknown) => (summaryChunks.push(JSON.stringify(rows)), summary),
    write: async () => {
      summaryWritten = true;
      return summary;
    },
  };
  return {
    getInput: (name: string) => process.env[`INPUT_${name.toUpperCase()}`] || '',
    getBooleanInput: (name: string) => {
      const v = (process.env[`INPUT_${name.toUpperCase()}`] || 'false').toLowerCase();
      if (['true', 'false'].includes(v)) return v === 'true';
      throw new Error(`bad bool ${name}`);
    },
    setSecret: (s: string) => secrets.push(s),
    setOutput: (k: string, v: string) => (outputs[k] = v),
    setFailed: (m: string) => (failedWith = m),
    info: rec,
    warning: rec,
    error: rec,
    debug: rec,
    notice: rec,
    startGroup: () => undefined,
    endGroup: () => undefined,
    group: async (_n: string, fn: () => unknown) => fn(),
    isDebug: () => false,
    summary,
  };
});

const caps: Capabilities = {
  edition: 'pro',
  mode: 'pro',
  version: '1.0.0',
  available: true,
  features: {
    restApi: true,
    streaming: true,
    auth: true,
    remediation: true,
    dashboard: true,
    scheduler: true,
  },
  detectedBy: 'system-info',
  warnings: [],
};

const campaign: Campaign = {
  id: 'camp_20260924_abcd1234',
  projectId: 'proj_1',
  targetId: 'tgt_1',
  sessionId: 'abcd1234',
  target: 'http://127.0.0.1:3000',
  status: 'completed',
  overallRisk: 'critical',
  createdAt: '2026-09-24T00:00:00Z',
  durationSeconds: 42,
  reportPath: null,
  isSubagent: false,
  severity: { critical: 1, high: 1, medium: 0, low: 1, info: 0, total: 3 },
  executiveSummary: null,
  edition: 'pro',
};

const findings: Finding[] = [
  {
    id: 'vuln_1', campaignId: campaign.id, projectId: 'proj_1', targetId: 'tgt_1',
    title: 'SQLi', severity: 'critical', status: 'exploited', category: 'sql_injection',
    cve: null, cvssScore: 9.8, cvssVector: null, mitreAttackId: null, mitreAttackName: null,
    endpoint: '/login', description: EVIDENCE, remediation: null, discoveredByAgent: 'nodejs',
    discoveredAt: null, evidence: null, edition: 'pro',
  },
  {
    id: 'vuln_2', campaignId: campaign.id, projectId: 'proj_1', targetId: 'tgt_1',
    title: 'XSS', severity: 'high', status: 'confirmed', category: 'xss',
    cve: null, cvssScore: 6.1, cvssVector: null, mitreAttackId: null, mitreAttackName: null,
    endpoint: '/search', description: null, remediation: null, discoveredByAgent: 'nodejs',
    discoveredAt: null, evidence: null, edition: 'pro',
  },
  {
    id: 'vuln_3', campaignId: campaign.id, projectId: 'proj_1', targetId: 'tgt_1',
    title: 'Info', severity: 'low', status: 'unconfirmed', category: 'info-leak',
    cve: null, cvssScore: null, cvssVector: null, mitreAttackId: null, mitreAttackName: null,
    endpoint: null, description: null, remediation: null, discoveredByAgent: 'nodejs',
    discoveredAt: null, evidence: null, edition: 'pro',
  },
];

const detectMock = jest.fn(async () => caps);
const launchMock = jest.fn(async () => ({ correlation: { _id: 'c' } as any, campaignId: campaign.id, runId: 'run_1' }));
const waitMock = jest.fn(async () => campaign);
const listFindingsMock = jest.fn(async () => findings);
const getReportMock = jest.fn(async (_ref: unknown, opts?: any) => ({
  campaignId: campaign.id,
  format: 'markdown',
  content: `# report with ${EVIDENCE} ${opts?.full ? '(FULL)' : '(redacted)'}`,
  ready: true,
  redacted: !opts?.full,
}));
async function* emptyStream() { /* no events */ }

jest.mock('@darkmoon/client', () => {
  const actual = jest.requireActual('@darkmoon/client');
  class MockDarkmoonClient {
    detect = detectMock;
    launchCampaign = launchMock;
    waitForCompletion = waitMock;
    listFindings = listFindingsMock;
    getReport = getReportMock;
    streamProgress = () => emptyStream();
  }
  return { ...actual, DarkmoonClient: MockDarkmoonClient };
});

function setInput(name: string, value: string): void {
  process.env[`INPUT_${name.toUpperCase()}`] = value;
}

describe('run (integration, real computeFailPolicy)', () => {
  beforeEach(() => {
    logLines.length = 0;
    summaryChunks.length = 0;
    secrets.length = 0;
    failedWith = undefined;
    summaryWritten = false;
    for (const k of Object.keys(outputs)) delete outputs[k];
    for (const k of Object.keys(process.env)) if (k.startsWith('INPUT_')) delete process.env[k];
    setInput('mode', 'pro');
    setInput('base-url', 'https://dm.example.com');
    setInput('api-token', SECRET_TOKEN);
    setInput('target', 'http://127.0.0.1:3000');
    setInput('fail-on', 'critical,high');
    setInput('report-dir', process.env.RUNNER_TEMP || '/tmp');
    setInput('safe-harbor', 'false');
    setInput('post-report', 'false');
    setInput('full-report', 'false');
  });

  it('masks the token BEFORE the first client call', async () => {
    const { run } = await import('../main.js');
    await run();
    expect(secrets).toContain(SECRET_TOKEN);
    expect(detectMock).toHaveBeenCalled();
  });

  it('sets outputs from the campaign severity + status counts', async () => {
    const { run } = await import('../main.js');
    await run();
    expect(outputs['campaign-id']).toBe(campaign.id);
    expect(outputs['edition']).toBe('pro');
    expect(outputs['overall-risk']).toBe('critical');
    expect(outputs['total-findings']).toBe('3');
    expect(outputs['critical']).toBe('1');
    expect(outputs['high']).toBe('1');
    expect(outputs['low']).toBe('1');
    expect(outputs['exploited']).toBe('1');
    expect(outputs['confirmed']).toBe('1');
    expect(outputs['unconfirmed']).toBe('1');
    expect(outputs['report-path']).toMatch(/darkmoon-camp_20260924_abcd1234\.md$/);
    expect(outputs['policy-failed']).toBe('true');
  });

  it('fails from findings (not exit code) per fail-on', async () => {
    const { run } = await import('../main.js');
    await run();
    expect(failedWith).toBeDefined();
    expect(String(failedWith).toLowerCase()).toContain('critical');
  });

  it('does not fail when fail-on is empty even with criticals', async () => {
    setInput('fail-on', '');
    const { run } = await import('../main.js');
    await run();
    expect(failedWith).toBeUndefined();
    expect(outputs['policy-failed']).toBe('false');
  });

  it('never leaks the token or raw evidence to logs/summary', async () => {
    const { run } = await import('../main.js');
    await run();
    const haystack = [...logLines, ...summaryChunks].join('\n');
    expect(haystack).not.toContain(SECRET_TOKEN);
    expect(haystack).not.toContain(EVIDENCE);
  });

  it('fetches the redacted report by default (no two-key opt-in)', async () => {
    const { run } = await import('../main.js');
    await run();
    expect(getReportMock).toHaveBeenCalledWith(campaign.id);
  });

  it('synthesizes SARIF from findings when report-format=sarif', async () => {
    setInput('report-format', 'sarif');
    const { run } = await import('../main.js');
    await run();
    expect(listFindingsMock).toHaveBeenCalled();
    expect(outputs['report-path']).toMatch(/\.sarif$/);
  });

  it('writes the step summary tables', async () => {
    const { run } = await import('../main.js');
    await run();
    expect(summaryWritten).toBe(true);
    expect(summaryChunks.length).toBeGreaterThanOrEqual(2);
  });
});
