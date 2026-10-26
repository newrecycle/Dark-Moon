/**
 * Node-only tests (no `vscode` import) so the data + safety logic can be
 * verified in environments without the Electron/GTK stack. These exercise the
 * exact code paths the extension uses for data loading, redaction and
 * capability degradation.
 */
import * as assert from 'assert';
import * as path from 'path';
import { createFixtureClient } from '../../src/darkmoon/fixtureClient';
import { redact } from '../../src/util/redact';

const FIXTURES = path.resolve(__dirname, '..', '..', '..', 'test', 'fixtures');

describe('fixtureClient data layer', () => {
  const oss = createFixtureClient({ dir: FIXTURES, edition: 'oss' });
  const pro = createFixtureClient({ dir: FIXTURES, edition: 'pro' });

  it('loads campaigns from real fixtures', async () => {
    const camps = await oss.listCampaigns();
    assert.ok(camps.length >= 2, `expected campaigns, got ${camps.length}`);
    assert.ok(camps[0].id.startsWith('camp_'));
    assert.ok(camps.every((c) => 'stats' in c));
  });

  it('loads findings and links them to campaigns', async () => {
    const findings = await oss.listFindings();
    assert.ok(findings.length > 0);
    const camps = await oss.listCampaigns();
    const ids = new Set(camps.map((c) => c.id));
    assert.ok(findings.every((f) => ids.has(f.campaign_id)));
    const one = await oss.getFinding(findings[0].id);
    assert.strictEqual(one?.id, findings[0].id);
  });

  it('filters findings by campaign', async () => {
    const camps = await oss.listCampaigns();
    const target = camps.find((c) => (c.stats.total_findings ?? 0) > 0) ?? camps[0];
    const f = await oss.listFindings(target.id);
    assert.ok(f.every((x) => x.campaign_id === target.id));
  });

  it('lists reports', async () => {
    const reports = await oss.listReports();
    assert.ok(reports.length > 0);
    assert.ok(reports[0].id.length > 0);
  });

  it('report is REDACTED by default and rehydrated only on demand', async () => {
    const reports = await oss.listReports();
    const id = reports[0].id;
    const def = await oss.getReport(id);
    assert.strictEqual(def.rehydrated, false);
    assert.ok(!def.markdown.includes('127.0.0.1'), 'default report leaked an IP');

    const full = await oss.getReport(id, { rehydrate: true });
    assert.strictEqual(full.rehydrated, true);
    assert.ok(full.markdown.includes('127.0.0.1'), 'full report carries real values');
  });

  it('capability degradation: OSS vs Pro', async () => {
    const co = await oss.capabilities();
    assert.strictEqual(co.edition, 'oss');
    assert.strictEqual(co.liveStatus, false);
    assert.strictEqual(co.webDashboard, false);

    const cp = await pro.capabilities();
    assert.strictEqual(cp.edition, 'pro');
    assert.strictEqual(cp.liveStatus, true);
    assert.strictEqual(cp.webDashboard, true);
  });

  it('launchCampaign returns a queued campaign id (demo source)', async () => {
    const res = await oss.launchCampaign({ target: 'https://staging.example.com' });
    assert.ok(res.campaignId.startsWith('camp_'));
  });
});

describe('redaction net over real vuln evidence', () => {
  it('masks the AD kerberoast IP and cracked password shapes', () => {
    const sample =
      'nxc smb 192.168.56.10 -u svc_backup -p nikwengtuts ; token eyJabc.eyJdef.sig';
    const r = redact(sample);
    assert.ok(!r.includes('192.168.56.10'));
    assert.ok(!r.includes('eyJabc.eyJdef.sig'));
  });
});
