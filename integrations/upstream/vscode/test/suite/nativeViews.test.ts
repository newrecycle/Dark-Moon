import * as assert from 'assert';
import * as vscode from 'vscode';
import type { DarkmoonApi } from '../../src/extension';
import { fakeClientFactory } from '../fakeClient';
import { CampaignsTreeProvider } from '../../src/views/campaignsTree';
import { ReportsTreeProvider } from '../../src/views/reportsView';
import { VulnerabilitiesViewProvider } from '../../src/views/vulnerabilitiesView';

describe('Native packaged extension views and identity boundaries', () => {
  it('renders campaign/finding/report providers against the activated extension', async () => {
    const ext = vscode.extensions.getExtension<DarkmoonApi>('darkmoon.darkmoon-vscode');
    assert.ok(ext && ext.extensionPath.includes('vscode-package'),
      'Test must activate the VSIX contents, not the extension source tree');
    const api = await ext!.activate();
    api.setClientFactory(fakeClientFactory);
    await vscode.workspace.getConfiguration('darkmoon').update('mode', 'oss',
      vscode.ConfigurationTarget.Global);
    await api.session.refresh();
    assert.ok(!api.session.snapshot.error, 'Connected offline fixture session');

    const campaignTree = new CampaignsTreeProvider(api.session);
    const reportTree = new ReportsTreeProvider(api.session);
    const camps = campaignTree.getChildren();
    assert.ok(camps.length > 0, 'real campaign view provider has rows');
    const campItem = campaignTree.getTreeItem(camps[0]);
    assert.ok(String(campItem.id).startsWith('campaign:'));
    const children = campaignTree.getChildren(camps[0]);
    assert.ok(children.some(node => campaignTree.getTreeItem(node).contextValue === 'darkmoon.finding'));
    assert.ok(reportTree.getChildren().length > 0, 'real reports provider has rows');
    assert.ok(reportTree.getTreeItem(reportTree.getChildren()[0]).id?.startsWith('report:'));

    // Resolve the *actual* VS Code WebviewViewProvider with a recording
    // WebviewView. Real HTML construction and message dispatch execute here;
    // only the Electron DOM surface is replaced.
    const messages: unknown[] = [];
    let receive: (value: unknown) => void = () => {};
    const webview = {
      options: {}, html: '', cspSource: 'vscode-webview:',
      asWebviewUri: (uri: vscode.Uri) => uri,
      postMessage: async (msg: unknown) => { messages.push(msg); return true; },
      onDidReceiveMessage: (listener: (msg: unknown) => void) => {
        receive = listener; return { dispose() {} };
      },
    };
    const view = new VulnerabilitiesViewProvider(ext!.extensionUri, api.session);
    view.resolveWebviewView({webview} as unknown as vscode.WebviewView);
    assert.match(webview.html, /Content-Security-Policy/);
    receive({ type: 'ready' });
    const frames = messages as Array<{type: string; rows: Array<{id: string; campaign: string}>}>;
    const rows = frames.filter(frame => frame.type === 'rows').at(-1)?.rows ?? [];
    assert.ok(rows.length > 0, 'view receives actual finding rows');
    assert.ok(rows.every(row => row.id && typeof row.campaign === 'string'));
    assert.ok(rows.every(row => !row.campaign.includes('127.0.0.1')),
      'default vulnerability list must redact the target host');
    for (const finding of api.session.snapshot.findings) {
      assert.ok(api.session.snapshot.campaigns.some(c => c.id === finding.campaign_id),
        'exact campaign id rather than a run id');
    }
    assert.strictEqual(api.session.getFinding('deleted_finding_absent'), undefined);
  });
});
