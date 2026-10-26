import * as vscode from 'vscode';
import type { Campaign, Finding } from '../darkmoon/contract';
import { DarkmoonSession } from '../session';
import { severityIcon } from '../util/severity';

type Node = CampaignNode | InfoNode | FindingNode;

class CampaignNode {
  readonly kind = 'campaign' as const;
  constructor(public readonly campaign: Campaign) {}
}
class InfoNode {
  readonly kind = 'info' as const;
  constructor(
    public readonly label: string,
    public readonly value: string,
    public readonly icon?: string
  ) {}
}
class FindingNode {
  readonly kind = 'finding' as const;
  constructor(public readonly finding: Finding) {}
}

export class CampaignsTreeProvider implements vscode.TreeDataProvider<Node> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<
    Node | undefined | null | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(private readonly session: DarkmoonSession) {
    session.onDidChange(() => this._onDidChangeTreeData.fire());
  }

  getTreeItem(node: Node): vscode.TreeItem {
    switch (node.kind) {
      case 'campaign': {
        const c = node.campaign;
        const item = new vscode.TreeItem(
          c.target ?? c.id,
          vscode.TreeItemCollapsibleState.Collapsed
        );
        const total = c.stats?.total_findings ?? 0;
        item.description = `${c.status}${total ? ` · ${total} findings` : ''}`;
        item.tooltip = new vscode.MarkdownString(
          [
            `**${c.target ?? c.id}**`,
            `- ID: \`${c.id}\``,
            `- Status: ${c.status}`,
            c.overall_risk ? `- Overall risk: **${c.overall_risk}**` : '',
            c.date ? `- Date: ${c.date}` : '',
            c.methodology ? `- Methodology: ${c.methodology}` : '',
          ]
            .filter(Boolean)
            .join('\n')
        );
        item.iconPath = new vscode.ThemeIcon('target');
        item.contextValue = 'darkmoon.campaign';
        item.id = `campaign:${c.id}`;
        return item;
      }
      case 'info': {
        const item = new vscode.TreeItem(
          `${node.label}: ${node.value}`,
          vscode.TreeItemCollapsibleState.None
        );
        if (node.icon) {
          item.iconPath = new vscode.ThemeIcon(node.icon);
        }
        item.contextValue = 'darkmoon.info';
        return item;
      }
      case 'finding': {
        const f = node.finding;
        const item = new vscode.TreeItem(
          f.title,
          vscode.TreeItemCollapsibleState.None
        );
        item.description = `${f.severity}${
          f.cvss_score != null ? ` · ${f.cvss_score}` : ''
        }`;
        item.iconPath = severityIcon(f.severity);
        item.contextValue = 'darkmoon.finding';
        item.command = {
          command: 'darkmoon.openFinding',
          title: 'Open finding',
          arguments: [f.id],
        };
        item.tooltip = new vscode.MarkdownString(
          `**${f.title}**\n\n${f.status} · ${f.category ?? ''}`
        );
        return item;
      }
    }
  }

  getChildren(node?: Node): Node[] {
    const snap = this.session.snapshot;
    if (!node) {
      if (snap.error) {
        return [new InfoNode('Not available', snap.error, 'warning')];
      }
      if (snap.loading && snap.campaigns.length === 0) {
        return [new InfoNode('Loading', '…', 'loading~spin')];
      }
      if (snap.campaigns.length === 0) {
        return [new InfoNode('No campaigns', 'Run a campaign to begin', 'info')];
      }
      return snap.campaigns.map((c) => new CampaignNode(c));
    }
    if (node.kind === 'campaign') {
      const c = node.campaign;
      const children: Node[] = [];
      if (c.overall_risk) {
        children.push(new InfoNode('Risk', String(c.overall_risk), 'pulse'));
      }
      const s = c.stats ?? {};
      const parts = (['critical', 'high', 'medium', 'low', 'info'] as const)
        .map((k) => (s[k] ? `${s[k]} ${k}` : ''))
        .filter(Boolean)
        .join(', ');
      if (parts) {
        children.push(new InfoNode('Severity', parts, 'graph'));
      }
      for (const a of c.agents_dispatched ?? []) {
        children.push(
          new InfoNode(`Agent ${a.agent}`, `${a.findings} findings`, 'robot')
        );
      }
      const findings = this.session.findingsForCampaign(c.id);
      for (const f of findings) {
        children.push(new FindingNode(f));
      }
      return children;
    }
    return [];
  }
}
