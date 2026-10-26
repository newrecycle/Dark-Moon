import * as assert from 'assert';
import * as vscode from 'vscode';
import { fakeClientFactory } from '../fakeClient';
import type { DarkmoonApi } from '../../src/extension';
import { ReportContentProvider } from '../../src/views/reportsView';

const EXT_ID = 'darkmoon.darkmoon-vscode';

async function getApi(mode: 'oss' | 'pro'): Promise<DarkmoonApi> {
  const ext = vscode.extensions.getExtension<DarkmoonApi>(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} must be present`);
  const api = await ext!.activate();
  // Force mode so the fake factory reports the right edition.
  await vscode.workspace
    .getConfiguration('darkmoon')
    .update('mode', mode, vscode.ConfigurationTarget.Global);
  api.setClientFactory(fakeClientFactory);
  await api.session.refresh();
  return api;
}

describe('Darkmoon extension activation & data (plan §5)', () => {
  it('activates and registers commands', async () => {
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext, 'extension present');
    await ext!.activate();
    const cmds = await vscode.commands.getCommands(true);
    for (const c of [
      'darkmoon.refresh',
      'darkmoon.launchCampaign',
      'darkmoon.openFinding',
      'darkmoon.openReport',
      'darkmoon.openReportFull',
      'darkmoon.setToken',
      'darkmoon.setLicense',
    ]) {
      assert.ok(cmds.includes(c), `command ${c} registered`);
    }
  });

  it('loads campaigns, findings and reports (OSS)', async () => {
    const api = await getApi('oss');
    const snap = api.session.snapshot;
    assert.strictEqual(snap.error, undefined, snap.error);
    assert.ok(snap.campaigns.length > 0, 'has campaigns');
    assert.ok(snap.findings.length > 0, 'has findings');
    assert.ok(snap.reports.length > 0, 'has reports');
    assert.strictEqual(snap.capabilities?.edition, 'oss');
  });

  it('capability degradation: OSS hides live status & dashboard, Pro enables them', async () => {
    const oss = await getApi('oss');
    assert.strictEqual(oss.session.capabilities?.liveStatus, false);
    assert.strictEqual(oss.session.capabilities?.webDashboard, false);

    const pro = await getApi('pro');
    assert.strictEqual(pro.session.capabilities?.edition, 'pro');
    assert.strictEqual(pro.session.capabilities?.liveStatus, true);
    assert.strictEqual(pro.session.capabilities?.webDashboard, true);
  });

  it('findings link to their campaign', async () => {
    const api = await getApi('oss');
    const camp = api.session.snapshot.campaigns[0];
    const findings = api.session.findingsForCampaign(camp.id);
    assert.ok(findings.length > 0, 'campaign has findings');
    assert.ok(findings.every((f) => f.campaign_id === camp.id));
  });

  it('opening a finding does not throw', async () => {
    const api = await getApi('oss');
    const finding = api.session.snapshot.findings[0];
    await vscode.commands.executeCommand('darkmoon.openFinding', finding.id);
  });

  it('report preview is REDACTED by default and rehydrated only on demand', async () => {
    const api = await getApi('oss');
    const report = api.session.snapshot.reports[0];
    const provider = new ReportContentProvider(api.session);

    const redactedUri = ReportContentProvider.uri(report.id, false);
    const redacted = await provider.provideTextDocumentContent(redactedUri);
    assert.ok(redacted.length > 0);
    // The real report fixture contains 127.0.0.1 — must be masked by default.
    assert.ok(
      !redacted.includes('127.0.0.1'),
      'default preview must not leak real IPs'
    );

    const fullUri = ReportContentProvider.uri(report.id, true);
    const full = await provider.provideTextDocumentContent(fullUri);
    assert.ok(
      full.includes('127.0.0.1') || full.includes('real infrastructure'),
      'full report carries rehydrated content'
    );
  });

  it('launchCampaign is guarded by capability (no throw path)', async () => {
    const api = await getApi('oss');
    // Just ensure the capability flag the command checks is present.
    assert.strictEqual(api.session.capabilities?.launchCampaign, true);
  });
});
