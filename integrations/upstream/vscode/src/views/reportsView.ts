import * as vscode from 'vscode';
import type { ReportMeta } from '../darkmoon/contract';
import { DarkmoonSession } from '../session';
import { RevealGrants, type RevealContext } from '../util/reveal';
import { revealContext } from '../util/localReveal';

export const REPORT_SCHEME = 'darkmoon-report';

/** Read-only metadata previews; full bodies require an in-memory reveal grant. */
export class ReportContentProvider implements vscode.TextDocumentContentProvider, vscode.Disposable {
  private readonly _onDidChange = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this._onDidChange.event;
  private readonly fullUris = new Map<string, vscode.Uri>();
  private readonly grants: RevealGrants;
  private readonly subscriptions: vscode.Disposable[];

  constructor(private readonly session: DarkmoonSession, ttlMs = 60_000) {
    this.grants = new RevealGrants(() => revealContext(session), token => {
      const uri = this.fullUris.get(token);
      this.fullUris.delete(token);
      if (uri) this._onDidChange.fire(uri);
    }, ttlMs);
    this.subscriptions = [
      session.onDidChange(() => this.grants.invalidate()),
      vscode.window.onDidChangeWindowState(state => { if (!state.focused) this.grants.invalidate(); }),
    ];
  }

  static uri(id: string, rehydrate = false): vscode.Uri {
    // A legacy flag never grants access; only authorizeFull can issue a grant.
    return vscode.Uri.from({ scheme: REPORT_SCHEME, path: `/${encodeURIComponent(id)}.md`, query: rehydrate ? 'rehydrate=1' : '' });
  }

  authorizeFull(id: string, expected: RevealContext): vscode.Uri | undefined {
    if (!this.session.snapshot.reports.some(report => report.id === id)) return undefined;
    const token = this.grants.issue(id, expected);
    if (!token) return undefined;
    const uri = ReportContentProvider.uri(id).with({ query: `grant=${token}` });
    this.fullUris.set(token, uri);
    return uri;
  }

  private preview(id: string): string {
    const campaign = this.session.getCampaign(id);
    if (!campaign || !/^[A-Za-z0-9_-]{1,200}$/.test(id) || !this.session.getClient()) return '# Report unavailable\n\nRefresh the connection to load current metadata.';
    // Free-form markdown can contain credentials that no pattern can recognize.
    // The default view is built solely from the current campaign's typed counts.
    const rows = ['critical', 'high', 'medium', 'low', 'info'].map(severity => {
      const value = campaign.stats[severity as keyof typeof campaign.stats];
      return `| ${severity} | ${typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 'unavailable'} |`;
    });
    return `# Assessment report\n\nCampaign: ${id}\n\nThese are retained campaign summary counts, not proof of successful validation. Detailed report text and evidence are hidden. Use Darkmoon: Open Full Report on a trusted local workbench to reveal for up to 60 seconds.\n\n| Severity | Findings |\n| --- | ---: |\n${rows.join('\n')}\n`;
  }

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    let id: string;
    try { id = decodeURIComponent(uri.path.replace(/^\//, '').replace(/\.md$/, '')); }
    catch { return '# Report unavailable'; }
    const params = new URLSearchParams(uri.query);
    const token = params.getAll('grant').length === 1 && [...params.keys()].every(key => key === 'grant') ? params.get('grant')! : '';
    const client = this.session.getClient();
    if (!client || !this.grants.valid(token, id)) return this.preview(id);
    try {
      const result = await client.getReport(id, { rehydrate: true });
      if (!this.grants.valid(token, id) || client !== this.session.getClient()) return this.preview(id);
      if (!result.rehydrated) return this.preview(id);
      return '> Full report — real infrastructure values shown. Access expires within 60 seconds.\n\n' + result.markdown;
    } catch {
      return '# Report unavailable\n\nThe current credentials could not read this report.';
    }
  }

  dispose(): void {
    for (const subscription of this.subscriptions) subscription.dispose();
    this.grants.dispose();
    this.fullUris.clear();
    this._onDidChange.dispose();
  }
}

type ReportNode = ReportMeta | { placeholder: string; icon?: string };

export class ReportsTreeProvider implements vscode.TreeDataProvider<ReportNode> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private readonly session: DarkmoonSession) {
    session.onDidChange(() => this._onDidChangeTreeData.fire());
  }

  getTreeItem(node: ReportNode): vscode.TreeItem {
    if ('placeholder' in node) {
      const item = new vscode.TreeItem(
        node.placeholder,
        vscode.TreeItemCollapsibleState.None
      );
      if (node.icon) {
        item.iconPath = new vscode.ThemeIcon(node.icon);
      }
      return item;
    }
    const item = new vscode.TreeItem(
      node.title ?? node.id,
      vscode.TreeItemCollapsibleState.None
    );
    item.description = node.generatedAt ?? '';
    item.iconPath = new vscode.ThemeIcon('file-text');
    item.contextValue = 'darkmoon.report';
    item.id = `report:${node.id}`;
    item.command = {
      command: 'darkmoon.openReport',
      title: 'Open report (redacted)',
      arguments: [node.id],
    };
    item.tooltip = new vscode.MarkdownString(
      `**${node.title ?? node.id}**\n\nOpens a redacted preview. Right-click for the full (local-only) report.`
    );
    return item;
  }

  getChildren(): ReportNode[] {
    const snap = this.session.snapshot;
    if (snap.error) {
      return [{ placeholder: snap.error, icon: 'warning' }];
    }
    if (snap.reports.length === 0) {
      return [
        {
          placeholder: snap.loading ? 'Loading…' : 'No reports yet',
          icon: snap.loading ? 'loading~spin' : 'info',
        },
      ];
    }
    return snap.reports;
  }
}
