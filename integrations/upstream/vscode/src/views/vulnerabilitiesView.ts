import * as vscode from 'vscode';
import { DarkmoonSession } from '../session';
import { csp, getNonce, mediaUri } from '../util/html';
import { severityRank } from '../util/severity';
import { redact } from '../util/redact';

interface Row {
  id: string;
  severity: string;
  severityRank: number;
  title: string;
  category: string;
  component: string;
  status: string;
  campaign: string;
  cvss: number | null;
}

/**
 * Rich vulnerabilities table (plan §3.4): filter by severity/status, free-text
 * search and column sort — a tree view cannot express this. Rendered in a
 * webview VIEW inside the Darkmoon activity-bar container.
 */
export class VulnerabilitiesViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'darkmoon.vulnerabilities';
  private view?: vscode.WebviewView;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly session: DarkmoonSession
  ) {
    session.onDidChange(() => this.postRows());
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'media')],
    };
    webviewView.webview.html = this.html(webviewView.webview);
    webviewView.webview.onDidReceiveMessage((msg) => {
      if (msg?.type === 'ready') {
        this.postRows();
      } else if (msg?.type === 'open' && typeof msg.id === 'string') {
        void vscode.commands.executeCommand('darkmoon.openFinding', msg.id);
      }
    });
  }

  private rows(): Row[] {
    const snap = this.session.snapshot;
    const targetById = new Map(snap.campaigns.map((c) => [c.id, c.target ?? c.id]));
    return snap.findings.map((f) => ({
      id: f.id,
      severity: f.severity,
      severityRank: severityRank(f.severity),
      title: f.title,
      category: f.category ?? '',
      // Component describes the vuln class/route (low risk); redact as a net.
      component: redact(f.plugin_or_component || f.endpoint || ''),
      status: String(f.status),
      // Campaign target can be a real host — redacted by default (plan §4).
      campaign: redact(targetById.get(f.campaign_id) ?? f.campaign_id),
      cvss: f.cvss_score ?? null,
    }));
  }

  private postRows(): void {
    if (!this.view) {
      return;
    }
    const snap = this.session.snapshot;
    void this.view.webview.postMessage({
      type: 'rows',
      rows: this.rows(),
      error: snap.error,
      loading: snap.loading,
    });
  }

  private html(webview: vscode.Webview): string {
    const nonce = getNonce();
    const script = mediaUri(webview, this.extensionUri, 'media', 'vulnerabilities.js');
    const style = mediaUri(webview, this.extensionUri, 'media', 'vulnerabilities.css');
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="${csp(webview, nonce)}" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link href="${style}" rel="stylesheet" />
<title>Vulnerabilities</title>
</head>
<body>
<div class="toolbar">
  <input id="search" type="search" placeholder="Search title, type, component…" aria-label="Search vulnerabilities" />
  <select id="sev" aria-label="Filter by severity">
    <option value="">All severities</option>
    <option value="critical">Critical</option>
    <option value="high">High</option>
    <option value="medium">Medium</option>
    <option value="low">Low</option>
    <option value="info">Info</option>
  </select>
  <select id="status" aria-label="Filter by status">
    <option value="">All statuses</option>
    <option value="exploited">Exploited</option>
    <option value="confirmed">Confirmed</option>
    <option value="unconfirmed">Unconfirmed</option>
    <option value="remediated">Remediated</option>
  </select>
</div>
<div id="count" class="count"></div>
<table id="table">
  <thead>
    <tr>
      <th data-sort="severityRank">Severity</th>
      <th data-sort="title">Title / Type</th>
      <th data-sort="component">Target / Component</th>
      <th data-sort="status">Status</th>
      <th data-sort="campaign">Campaign</th>
    </tr>
  </thead>
  <tbody id="rows"></tbody>
</table>
<div id="empty" class="empty" hidden></div>
<script nonce="${nonce}" src="${script}"></script>
</body>
</html>`;
  }
}
