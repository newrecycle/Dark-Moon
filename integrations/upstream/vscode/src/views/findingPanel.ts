import * as vscode from 'vscode';
import type { Finding } from '../darkmoon/contract';
import { DarkmoonSession } from '../session';
import { csp, getNonce, mediaUri } from '../util/html';
import { redactFinding } from '../util/redact';

/**
 * Finding detail (plan §3.4): description, evidence, remediation in a webview
 * PANEL. Redaction-safe (plan §4): shows redacted content by default; real
 * values are revealed only on an explicit user action, and only when the
 * workbench is local (never over a remote/untrusted connection).
 */
export class FindingPanelManager {
  private readonly panels = new Map<string, vscode.WebviewPanel>();

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly session: DarkmoonSession
  ) {}

  private isLocal(): boolean {
    // No remote authority => local desktop workbench.
    return !vscode.env.remoteName;
  }

  async open(findingId: string): Promise<void> {
    const finding = this.session.getFinding(findingId);
    if (!finding) {
      void vscode.window.showWarningMessage(`Darkmoon: finding ${findingId} not found.`);
      return;
    }
    const existing = this.panels.get(findingId);
    if (existing) {
      existing.reveal();
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      'darkmoon.finding',
      finding.title.slice(0, 60),
      vscode.ViewColumn.Active,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'media')],
      }
    );
    panel.iconPath = vscode.Uri.joinPath(
      this.extensionUri,
      'resources',
      'darkmoon.svg'
    );
    this.panels.set(findingId, panel);
    panel.onDidDispose(() => this.panels.delete(findingId));

    panel.webview.html = this.html(panel.webview);
    panel.webview.onDidReceiveMessage(async (msg) => {
      if (msg?.type === 'ready') {
        this.post(panel, finding, false);
      } else if (msg?.type === 'reveal') {
        if (!this.isLocal()) {
          void vscode.window.showWarningMessage(
            'Darkmoon: revealing real values is disabled on remote/untrusted workbenches.'
          );
          this.post(panel, finding, false);
          return;
        }
        const ok = await vscode.window.showWarningMessage(
          'Reveal real infrastructure values (IPs, hosts, credentials) in this finding? They will be shown in plain text.',
          { modal: true },
          'Reveal'
        );
        this.post(panel, finding, ok === 'Reveal');
      }
    });
  }

  private post(
    panel: vscode.WebviewPanel,
    finding: Finding,
    rehydrated: boolean
  ): void {
    const payload = rehydrated ? finding : redactFinding(finding);
    void panel.webview.postMessage({
      type: 'finding',
      finding: payload,
      rehydrated,
      canReveal: this.isLocal(),
    });
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
