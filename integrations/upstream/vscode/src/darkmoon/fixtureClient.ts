/**
 * Fixture-backed Darkmoon client.
 *
 * This is NOT a reimplementation of `@darkmoon/client`'s OSS-CLI / Pro-REST
 * adapters. It is a static demo/test data source that satisfies the frozen
 * `DarkmoonClient` contract by reading canned artifacts (the same real
 * campaign/vulns/report JSON that ships with @darkmoon/client fixtures).
 *
 * It powers:
 *   - the headless integration tests (deterministic data), and
 *   - the installed-.vsix smoke test via `darkmoon.dev.useFixtures`
 *     (so the whole pipeline runs before the real package is linkable).
 *
 * The production data path is `@darkmoon/client` (see clientLoader.ts).
 */
import * as fs from 'fs';
import * as path from 'path';
import type {
  Campaign,
  Capabilities,
  ClientConfig,
  DarkmoonClient,
  Edition,
  Finding,
  LaunchOptions,
  LaunchResult,
  ReportContent,
  ReportMeta,
} from './contract';
import { redact } from '../util/redact';

interface FixtureClientOptions {
  dir: string;
  edition: Edition;
}

function readJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(file, 'utf8')) as T;
}

function safeList(dir: string): string[] {
  try {
    return fs.readdirSync(dir);
  } catch {
    return [];
  }
}

export function createFixtureClient(opts: FixtureClientOptions): DarkmoonClient {
  const ossDir = path.join(opts.dir, 'oss');
  const edition = opts.edition;

  const loadOssCampaigns = (): Campaign[] => {
    const out: Campaign[] = [];
    for (const f of safeList(ossDir)) {
      if (f.endsWith('.campaign.json')) {
        const c = readJson<Campaign>(path.join(ossDir, f));
        if (!c.target && c.report_path) {
          const m = /pentest_report_(.+?)_\d{8}/.exec(c.report_path);
          if (m) {
            c.target = m[1].replace(/_/g, ':');
          }
        }
        out.push(c);
      }
    }
    return out.sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''));
  };

  const loadOssFindings = (campaignId?: string): Finding[] => {
    const out: Finding[] = [];
    for (const f of safeList(ossDir)) {
      if (f.endsWith('.vulns.json')) {
        const arr = readJson<Finding[]>(path.join(ossDir, f));
        for (const v of arr) {
          if (!campaignId || v.campaign_id === campaignId) {
            out.push(v);
          }
        }
      }
    }
    return out;
  };

  const capabilities = (): Capabilities => ({
    edition,
    launchCampaign: true,
    liveStatus: edition === 'pro',
    rehydratedReports: true,
    webDashboard: edition === 'pro',
  });

  return {
    async capabilities() {
      return capabilities();
    },
    async listCampaigns() {
      return loadOssCampaigns();
    },
    async getCampaign(id) {
      const c = loadOssCampaigns().find((x) => x.id === id);
      if (!c) {
        throw new Error(`campaign not found: ${id}`);
      }
      return c;
    },
    async listFindings(campaignId) {
      return loadOssFindings(campaignId);
    },
    async getFinding(id) {
      return loadOssFindings().find((f) => f.id === id);
    },
    async listReports(): Promise<ReportMeta[]> {
      const metas: ReportMeta[] = [];
      for (const f of safeList(ossDir)) {
        if (f.startsWith('report_') && f.endsWith('.md')) {
          const id = f.replace(/^report_/, '').replace(/\.md$/, '');
          const camp = loadOssCampaigns().find((c) => c.id.includes(id));
          metas.push({
            id,
            campaignId: camp?.id,
            title: camp?.target ? `Report — ${camp.target}` : `Report ${id}`,
            target: camp?.target,
            generatedAt: camp?.date,
            path: camp?.report_path,
          });
        }
      }
      return metas;
    },
    async getReport(id, reportOpts): Promise<ReportContent> {
      const file = path.join(ossDir, `report_${id}.md`);
      let markdown: string;
      try {
        markdown = fs.readFileSync(file, 'utf8');
      } catch {
        throw new Error(`report not found: ${id}`);
      }
      const rehydrate = reportOpts?.rehydrate === true;
      if (rehydrate) {
        return { markdown, rehydrated: true };
      }
      return { markdown: redact(markdown), rehydrated: false };
    },
    async launchCampaign(_launch: LaunchOptions): Promise<LaunchResult> {
      // Demo/test data source: does not execute anything. The real client
      // performs the OSS CLI invocation / Pro REST POST.
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      return {
        campaignId: `camp_${stamp}_demo${Math.random().toString(16).slice(2, 8)}`,
        status: 'queued',
      };
    },
  };
}

/** Resolve a fixtures directory + edition from client config + env. */
export function fixtureClientFromConfig(
  cfg: ClientConfig,
  fallbackDir: string
): DarkmoonClient {
  const dir = process.env.DARKMOON_FIXTURES || cfg.dataDir || fallbackDir;
  const edition: Edition = cfg.mode === 'pro' ? 'pro' : 'oss';
  return createFixtureClient({ dir, edition });
}
