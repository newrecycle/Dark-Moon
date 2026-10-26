import * as vscode from 'vscode';
import { DarkmoonSession } from './session';
import { SecretsStore } from './secrets';
import { CampaignsTreeProvider } from './views/campaignsTree';
import { VulnerabilitiesViewProvider } from './views/vulnerabilitiesView';
import { FindingPanelManager } from './views/findingPanel';
import {
  ReportContentProvider,
  ReportsTreeProvider,
  REPORT_SCHEME,
} from './views/reportsView';
import { registerCommands } from './commands';
import { setClientFactory } from './darkmoon/clientLoader';
import { maybeShowStarCta } from './growthCta';
import type { CreateClient } from './darkmoon/contract';

export interface DarkmoonApi {
  session: DarkmoonSession;
  /** Test seam: inject a client factory, then call session.refresh(). */
  setClientFactory(factory: CreateClient | undefined): void;
}

export function activate(context: vscode.ExtensionContext): DarkmoonApi {
  const secrets = new SecretsStore(context.secrets);
  const session = new DarkmoonSession(context, secrets);
  context.subscriptions.push({ dispose: () => session.dispose() });

  // Campaigns — TreeDataProvider.
  const campaignsProvider = new CampaignsTreeProvider(session);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('darkmoon.campaigns', campaignsProvider)
  );

  // Vulnerabilities — rich webview view.
  const vulnProvider = new VulnerabilitiesViewProvider(
    context.extensionUri,
    session
  );
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      VulnerabilitiesViewProvider.viewType,
      vulnProvider
    )
  );

  // Reports — tree list + read-only virtual markdown documents.
  const reportsProvider = new ReportsTreeProvider(session);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('darkmoon.reports', reportsProvider)
  );
  const reportContentProvider = new ReportContentProvider(session);
  context.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider(
      REPORT_SCHEME,
      reportContentProvider
    )
  );

  // Finding detail — webview panels.
  const findingPanels = new FindingPanelManager(context.extensionUri, session);

  registerCommands(context, {
    session,
    findingPanels,
    reportProvider: reportContentProvider,
    secrets,
  });

  // Re-resolve when config or secrets change.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('darkmoon')) {
        void session.refresh();
      }
    }),
    secrets.onDidChange((e) => {
      if (e.key.startsWith('darkmoon.')) {
        void session.refresh();
      }
    })
  );

  // One-time, non-intrusive GitHub star CTA on first real value.
  maybeShowStarCta(context, session);

  void session.refresh();

  return {
    session,
    setClientFactory: (factory) => setClientFactory(factory),
  };
}

export function deactivate(): void {
  /* subscriptions are disposed by VS Code */
}
