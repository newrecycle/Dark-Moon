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
  private generation = 0;
  get revision(): number { return this.generation; }
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
    const revision = ++this.generation;
    const previous = this.client;
    this.client = undefined;
    this.data = { campaigns: [], findings: [], reports: [], loading: true };
    this._onDidChange.fire(this.data);
    void previous?.dispose?.();
    let candidate: DarkmoonClient | undefined;
    try {
      const settings = this.settings();
      const secretVals = await this.secrets.read();
      if (revision !== this.generation) return;
      const cfg = toClientConfig(settings, secretVals);
      candidate = await resolveClient(cfg, { fixturesDir: this.fixturesDir(), useFixtures: settings.useFixtures });
      if (revision !== this.generation) { void candidate.dispose?.(); return; }
      const capabilities = await candidate.capabilities();
      if (revision !== this.generation) { void candidate.dispose?.(); return; }
      const [campaigns, findings, reports] = await Promise.all([
        candidate.listCampaigns(), candidate.listFindings(), candidate.listReports(),
      ]);
      if (revision !== this.generation) { void candidate.dispose?.(); return; }
      this.client = candidate;
      this.data = { campaigns, findings, reports, capabilities, loading: false };
      await this.applyContext(capabilities, true);
    } catch {
      if (revision !== this.generation) { void candidate?.dispose?.(); return; }
      void candidate?.dispose?.();
      this.client = undefined;
      this.data = { campaigns: [], findings: [], reports: [], loading: false, error: 'Darkmoon data could not be refreshed. Check the connection and credentials.' };
      await this.applyContext(undefined, false);
    }
    if (revision === this.generation) this._onDidChange.fire(this.data);
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
    this.generation++;
    void this.client?.dispose?.();
    this.client = undefined;
    this._onDidChange.dispose();
  }
}
