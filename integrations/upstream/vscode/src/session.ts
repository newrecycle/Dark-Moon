import * as vscode from 'vscode';
import type {
  Campaign,
  Capabilities,
  DarkmoonClient,
  Finding,
  ReportMeta,
} from './darkmoon/contract';
import { readSettings, toClientConfig, type ExtensionSettings } from './config';
import { resolveClient } from './darkmoon/clientLoader';
import { SecretsStore } from './secrets';

export interface SessionData {
  campaigns: Campaign[];
  findings: Finding[];
  reports: ReportMeta[];
  capabilities?: Capabilities;
  error?: string;
  loading: boolean;
}

/**
 * Owns the resolved client, the loaded data and the capability-driven UI
 * context keys (plan §2.4 degradation). Views subscribe to `onDidChange`.
 */
export class DarkmoonSession {
  private readonly _onDidChange = new vscode.EventEmitter<SessionData>();
  readonly onDidChange = this._onDidChange.event;

  private client: DarkmoonClient | undefined;
  private data: SessionData = {
    campaigns: [],
    findings: [],
    reports: [],
    loading: false,
  };

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly secrets: SecretsStore
  ) {}

  get snapshot(): SessionData {
    return this.data;
  }

  get capabilities(): Capabilities | undefined {
    return this.data.capabilities;
  }

  getClient(): DarkmoonClient | undefined {
    return this.client;
  }

  private settings(): ExtensionSettings {
    return readSettings();
  }

  private fixturesDir(): string {
    return vscode.Uri.joinPath(this.context.extensionUri, 'resources', 'fixtures')
      .fsPath;
  }

  /** (Re)resolve the client and reload all data. */
  async refresh(): Promise<void> {
    this.data = { ...this.data, loading: true, error: undefined };
    this._onDidChange.fire(this.data);

    try {
      const settings = this.settings();
      const secretVals = await this.secrets.read();
      const cfg = toClientConfig(settings, secretVals);
      this.client = await resolveClient(cfg, {
        fixturesDir: this.fixturesDir(),
        useFixtures: settings.useFixtures,
      });

      const capabilities = await this.client.capabilities();
      const [campaigns, findings, reports] = await Promise.all([
        this.client.listCampaigns(),
        this.client.listFindings(),
        this.client.listReports(),
      ]);

      this.data = {
        campaigns,
        findings,
        reports,
        capabilities,
        loading: false,
        error: undefined,
      };
      await this.applyContext(capabilities, true);
    } catch (err) {
      this.data = {
        ...this.data,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      };
      await this.applyContext(undefined, false);
    }
    this._onDidChange.fire(this.data);
  }

  /**
   * Publish capability-driven context keys used by `when` clauses so Pro-only
   * features are hidden/disabled on OSS, and everything is hidden until ready.
   */
  private async applyContext(
    caps: Capabilities | undefined,
    ready: boolean
  ): Promise<void> {
    const set = (k: string, v: unknown) =>
      vscode.commands.executeCommand('setContext', k, v);
    await Promise.all([
      set('darkmoon.ready', ready),
      set('darkmoon.edition', caps?.edition ?? 'none'),
      set('darkmoon.cap.launchCampaign', ready && !!caps?.launchCampaign),
      set('darkmoon.cap.liveStatus', ready && !!caps?.liveStatus),
      set('darkmoon.cap.rehydratedReports', ready && !!caps?.rehydratedReports),
      set('darkmoon.cap.webDashboard', ready && !!caps?.webDashboard),
    ]);
  }

  findingsForCampaign(campaignId: string): Finding[] {
    return this.data.findings.filter((f) => f.campaign_id === campaignId);
  }

  getFinding(id: string): Finding | undefined {
    return this.data.findings.find((f) => f.id === id);
  }

  getCampaign(id: string): Campaign | undefined {
    return this.data.campaigns.find((c) => c.id === id);
  }

  dispose(): void {
    this._onDidChange.dispose();
    void this.client?.dispose?.();
  }
}
