import * as vscode from 'vscode';
import type { ReportMeta } from '../darkmoon/contract';
import { DarkmoonSession } from '../session';
import { redact } from '../util/redact';

export const REPORT_SCHEME = 'darkmoon-report';

/**
 * Read-only virtual documents for reports. Content-provider documents are not
 * editable, so the rendered markdown cannot be tampered with. Redaction is
 * decided by the `rehydrate` query flag (plan §4): default is redacted; the
 * rehydrated variant is only requested by an explicit local open.
 */
export class ReportContentProvider
  implements vscode.TextDocumentContentProvider
{
  private readonly _onDidChange = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this._onDidChange.event;

  constructor(private readonly session: DarkmoonSession) {}

  static uri(id: string, rehydrate: boolean): vscode.Uri {
    // Path ends in .md so VS Code assigns the markdown language + preview.
    return vscode.Uri.from({
      scheme: REPORT_SCHEME,
      path: `/${encodeURIComponent(id)}.md`,
      query: rehydrate ? 'rehydrate=1' : '',
    });
  }

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const client = this.session.getClient();
    const id = decodeURIComponent(uri.path.replace(/^\//, '').replace(/\.md$/, ''));
    const rehydrate = uri.query.includes('rehydrate=1');
    if (!client) {
      return '# Report unavailable\n\nDarkmoon client is not ready.';
    }
    try {
      const res = await client.getReport(id, { rehydrate });
      const header = rehydrate
        ? '> ⚠ **Full report — real infrastructure values shown.**\n\n'
        : '> Sensitive values are redacted. Use "Darkmoon: Open Full Report" (local only) to reveal.\n\n';
      // Defence-in-depth: for the default view always run the extension's own
      // redaction net, regardless of the client's redaction policy (which may
      // leave the target host visible). The full view is only reachable via an
      // explicit, local, confirmed action.
      const body = rehydrate ? res.markdown : redact(res.markdown);
      return header + body;
    } catch (err) {
      return `# Report unavailable\n\n${err instanceof Error ? err.message : String(err)}`;
    }
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
