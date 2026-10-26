import * as vscode from 'vscode';
import type { LaunchOptions, Severity } from './darkmoon/contract';
import { DarkmoonSession } from './session';
import { FindingPanelManager } from './views/findingPanel';
import { ReportContentProvider } from './views/reportsView';
import { SecretsStore } from './secrets';
import { baseUrlWarning, readSettings } from './config';

interface Deps {
  session: DarkmoonSession;
  findingPanels: FindingPanelManager;
  reportProvider: ReportContentProvider;
  secrets: SecretsStore;
}

export function registerCommands(
  context: vscode.ExtensionContext,
  deps: Deps
): void {
  const { session, findingPanels, secrets } = deps;
  const reg = (id: string, fn: (...a: any[]) => any) =>
    context.subscriptions.push(vscode.commands.registerCommand(id, fn));

  reg('darkmoon.refresh', () => session.refresh());

  reg('darkmoon.openFinding', (id: string) => findingPanels.open(id));

  reg('darkmoon.openReport', async (id: string) => {
    const uri = ReportContentProvider.uri(id, false);
    await openMarkdownPreview(uri);
  });

  reg('darkmoon.openReportFull', async (arg: unknown) => {
    const id = reportIdFromArg(arg);
    if (!id) {
      return;
    }
    if (vscode.env.remoteName) {
      void vscode.window.showWarningMessage(
        'Darkmoon: full (rehydrated) reports can only be opened on a local workbench.'
      );
      return;
    }
    const caps = session.capabilities;
    if (caps && !caps.rehydratedReports) {
      void vscode.window.showWarningMessage(
        'Darkmoon: this edition does not provide rehydrated reports.'
      );
      return;
    }
    const ok = await vscode.window.showWarningMessage(
      'Open the FULL report with real infrastructure values (IPs, hosts, credentials) in plain text?',
      { modal: true },
      'Open full report'
    );
    if (ok !== 'Open full report') {
      return;
    }
    const uri = ReportContentProvider.uri(id, true);
    await openMarkdownPreview(uri);
  });

  reg('darkmoon.launchCampaign', async () => {
    const caps = session.capabilities;
    if (!caps?.launchCampaign) {
      void vscode.window.showWarningMessage(
        'Darkmoon: launching campaigns is not available in the current mode.'
      );
      return;
    }
    const settings = readSettings();
    // OSS launch executes the local CLI — require workspace trust.
    if (caps.edition === 'oss' && !vscode.workspace.isTrusted) {
      void vscode.window.showWarningMessage(
        'Darkmoon: launching an OSS campaign runs the local CLI and requires a trusted workspace.'
      );
      return;
    }
    const warn = baseUrlWarning(settings.baseUrl);
    if (warn) {
      const proceed = await vscode.window.showWarningMessage(
        warn,
        { modal: true },
        'Proceed anyway'
      );
      if (proceed !== 'Proceed anyway') {
        return;
      }
    }
    const target = await vscode.window.showInputBox({
      title: 'Darkmoon — Launch campaign',
      prompt: 'Target you are AUTHORISED to assess (host:port or URL)',
      placeHolder: 'https://staging.example.com',
      ignoreFocusOut: true,
      validateInput: (v) => (v.trim() ? undefined : 'A target is required'),
    });
    if (!target) {
      return;
    }
    const confirm = await vscode.window.showWarningMessage(
      `Launch a Darkmoon campaign against "${target}"? Only test systems you are authorised to assess.`,
      { modal: true },
      'Launch'
    );
    if (confirm !== 'Launch') {
      return;
    }
    const noise = (await vscode.window.showQuickPick(
      ['(default)', 'stealth', 'low', 'moderate'],
      { title: 'Discovery aggressiveness (NOISE)', ignoreFocusOut: true }
    )) as string | undefined;
    const sev = (await vscode.window.showQuickPick(
      ['(none)', 'critical', 'high', 'medium', 'low', 'info'],
      { title: 'Global max severity cap (SEVERITY)', ignoreFocusOut: true }
    )) as string | undefined;
    const focus = await vscode.window.showInputBox({
      title: 'Attacks to prioritise (FOCUS) — optional',
      placeHolder: 'sqli,rce,ssrf,idor',
      ignoreFocusOut: true,
    });

    const opts: LaunchOptions = {
      target: target.trim(),
      focus: focus?.trim() || undefined,
      noise:
        noise && noise !== '(default)'
          ? (noise as LaunchOptions['noise'])
          : undefined,
      severityCap:
        sev && sev !== '(none)' ? (sev as Severity) : undefined,
    };

    const client = session.getClient();
    if (!client) {
      return;
    }
    try {
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Darkmoon: launching campaign…' },
        async () => {
          const res = await client.launchCampaign(opts);
          void vscode.window.showInformationMessage(
            `Darkmoon: campaign ${res.campaignId} (${res.status}).`
          );
        }
      );
      await session.refresh();
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Darkmoon: launch failed — ${err instanceof Error ? err.message : String(err)}`
      );
    }
  });

  reg('darkmoon.setToken', async () => {
    if (await secrets.setToken()) {
      await session.refresh();
    }
  });
  reg('darkmoon.setLicense', async () => {
    if (await secrets.setLicense()) {
      await session.refresh();
    }
  });
  reg('darkmoon.clearSecrets', async () => {
    const ok = await vscode.window.showWarningMessage(
      'Clear the stored Darkmoon token and license?',
      { modal: true },
      'Clear'
    );
    if (ok === 'Clear') {
      await secrets.clearAll();
      await session.refresh();
    }
  });
}

async function openMarkdownPreview(uri: vscode.Uri): Promise<void> {
  const doc = await vscode.workspace.openTextDocument(uri);
  // Render as a preview; fall back to the raw document if the built-in
  // markdown preview command is unavailable.
  try {
    await vscode.commands.executeCommand('markdown.showPreview', uri);
  } catch {
    await vscode.window.showTextDocument(doc, { preview: true });
  }
}

function reportIdFromArg(arg: unknown): string | undefined {
  if (typeof arg === 'string') {
    return arg;
  }
  if (arg && typeof arg === 'object' && 'id' in arg) {
    const id = (arg as { id?: string }).id;
    return id?.startsWith('report:') ? id.slice('report:'.length) : id;
  }
  return undefined;
}
