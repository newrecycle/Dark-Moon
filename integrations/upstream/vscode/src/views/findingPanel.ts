import * as vscode from 'vscode';
import type { Finding } from '../darkmoon/contract';
import { DarkmoonSession } from '../session';
import { csp, getNonce, mediaUri } from '../util/html';
import { redactFinding } from '../util/redact';
import { RevealGrants } from '../util/reveal';
import { revealContext } from '../util/localReveal';

/**
 * Finding detail (plan §3.4): description, evidence, remediation in a webview
 * PANEL. Redaction-safe (plan §4): shows redacted content by default; real
 * values are revealed only on an explicit user action, and only when the
 * workbench is local (never over a remote/untrusted connection).
 */
export class FindingPanelManager implements vscode.Disposable {
  private readonly panels = new Map<string, { panel: vscode.WebviewPanel; token?: string }>();
  private readonly grants: RevealGrants;
  private readonly subscriptions: vscode.Disposable[];

  constructor(private readonly extensionUri: vscode.Uri, private readonly session: DarkmoonSession) {
    this.grants = new RevealGrants(() => revealContext(session), token => {
      for (const [id, record] of this.panels) if (record.token === token) {
        record.token = undefined;
        this.post(id, record.panel);
      }
    });
    this.subscriptions = [
      session.onDidChange(() => { this.grants.invalidate(); for (const [id, record] of this.panels) this.post(id, record.panel); }),
      vscode.window.onDidChangeWindowState(state => { if (!state.focused) this.grants.invalidate(); }),
    ];
  }

  async open(findingId: string): Promise<void> {
    const finding = this.session.getFinding(findingId);
    if (!finding || !this.session.getClient()) {
      void vscode.window.showWarningMessage('Darkmoon: finding is unavailable; refresh the connection.');
      return;
    }
    const existing = this.panels.get(findingId);
    if (existing) { existing.panel.reveal(); return; }
    const panel = vscode.window.createWebviewPanel('darkmoon.finding', 'Darkmoon finding', vscode.ViewColumn.Active, {
      enableScripts: true,
      retainContextWhenHidden: false,
      localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'media')],
    });
    panel.iconPath = vscode.Uri.joinPath(this.extensionUri, 'resources', 'darkmoon.svg');
    const record: { panel: vscode.WebviewPanel; token?: string } = { panel };
    this.panels.set(findingId, record);
    panel.onDidDispose(() => { this.panels.delete(findingId); this.grants.invalidate(); });
    panel.onDidChangeViewState(() => { if (!panel.active) this.grants.invalidate(); });
    panel.webview.html = this.html(panel.webview);
    panel.webview.onDidReceiveMessage(async (message) => {
      if (message?.type === 'ready') this.post(findingId, panel);
      if (message?.type !== 'reveal') return;
      const expected = revealContext(this.session);
      const current = this.session.getFinding(findingId);
      if (!expected.allowed || !expected.client || !current || !panel.active) { this.post(findingId, panel); return; }
      const ok = await vscode.window.showWarningMessage('Reveal this finding’s detailed evidence and infrastructure values for up to 60 seconds?', { modal: true }, 'Reveal');
      if (ok !== 'Reveal' || !panel.active || this.panels.get(findingId) !== record) return;
      this.grants.invalidate();
      const token = this.grants.issue(findingId, expected);
      const client = this.session.getClient();
      if (!token || !client) { this.post(findingId, panel); return; }
      record.token = token;
      try {
        const fresh = await client.getFinding(findingId, { rehydrate: true });
        if (!this.grants.valid(token, findingId) || client !== this.session.getClient() || this.panels.get(findingId) !== record || !panel.active) return;
        if (!fresh || fresh.id !== findingId || fresh.campaign_id !== current.campaign_id) { this.grants.invalidate(); return; }
        void panel.webview.postMessage({ type: 'finding', finding: fresh, rehydrated: true, canReveal: true });
      } catch {
        this.grants.invalidate();
        this.post(findingId, panel);
      }
    });
  }

  private post(id: string, panel: vscode.WebviewPanel): void {
    const finding = this.session.getFinding(id);
    // Never send free-form evidence, descriptions, endpoints or remediation to
    // the default view. Regexes cannot identify every extracted credential.
    const preview: Finding = finding ? {
      id: finding.id, campaign_id: finding.campaign_id, title: finding.title,
      severity: finding.severity, status: finding.status, category: finding.category,
      cvss_score: finding.cvss_score, cve: finding.cve, mitre_attack_id: finding.mitre_attack_id,
      description: 'Detailed evidence and infrastructure values are hidden until an explicit reveal.',
    } : { id, campaign_id: '', title: 'Finding unavailable', severity: 'info', status: 'unknown', description: 'Refresh the connection to load this finding.' };
    void panel.webview.postMessage({ type: 'finding', finding: redactFinding(preview), rehydrated: false, canReveal: !!finding && revealContext(this.session).allowed });
  }

  dispose(): void {
    for (const subscription of this.subscriptions) subscription.dispose();
    this.grants.dispose();
    for (const record of this.panels.values()) record.panel.dispose();
    this.panels.clear();
  }

  private html(webview: vscode.Webview): string {
    const nonce = getNonce();
    const script = mediaUri(webview, this.extensionUri, 'media', 'finding.js');
    const style = mediaUri(webview, this.extensionUri, 'media', 'finding.css');
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="${csp(webview, nonce)}" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link href="${style}" rel="stylesheet" />
<title>Finding</title>
</head>
<body>
<div id="app"><p class="muted">Loading…</p></div>
<script nonce="${nonce}" src="${script}"></script>
</body>
</html>`;
  }
}
