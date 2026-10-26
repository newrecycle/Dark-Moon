/**
 * REAL end-to-end wiring test: drives the extension's adapter over the REAL
 * `@darkmoon/client` package (OSS backend) against the package's own dataroot
 * fixture tree. Proves the frozen-contract adapter maps real package output
 * into the shapes the extension UI consumes, including redaction gating.
 *
 * Skips itself cleanly if the package is not installed.
 */
import * as assert from 'assert';
import * as fs from 'fs';
import { createRealClient } from '../../src/darkmoon/realAdapter';
import { redact } from '../../src/util/redact';

const DATAROOT = '/home/mehdi/darkmoon-client/fixtures/dataroot';

function pkgAvailable(): boolean {
  try {
    require.resolve('@darkmoon/client');
    return fs.existsSync(DATAROOT);
  } catch {
    return false;
  }
}

(pkgAvailable() ? describe : describe.skip)(
  'E2E: extension adapter over real @darkmoon/client (OSS)',
  () => {
    const client = createRealClient({ mode: 'oss', dataDir: DATAROOT });

    it('detects OSS capabilities and degrades Pro-only features', async () => {
      const caps = await client.capabilities();
      assert.strictEqual(caps.edition, 'oss');
      assert.strictEqual(caps.liveStatus, false, 'OSS has no streaming');
      assert.strictEqual(caps.webDashboard, false, 'OSS has no dashboard');
    });

    it('lists campaigns mapped to the extension shape', async () => {
      const camps = await client.listCampaigns();
      const ids = camps.map((c) => c.id);
      assert.ok(ids.includes('camp_20260924_70602bf9'), 'known campaign present');
      const c = camps.find((x) => x.id === 'camp_20260924_70602bf9')!;
      assert.strictEqual(c.status, 'completed');
      assert.strictEqual(c.target, '127.0.0.1:3000');
      assert.ok((c.stats.total_findings ?? 0) >= 5);
    });

    it('lists findings with evidence mapped', async () => {
      const findings = await client.listFindings('camp_20260924_70602bf9');
      assert.ok(findings.length >= 5);
      assert.ok(findings.every((f) => f.campaign_id === 'camp_20260924_70602bf9'));
      assert.ok(
        ['critical', 'high', 'medium', 'low', 'info'].includes(findings[0].severity)
      );
    });

    it('report is redacted by default; full body only on two-key opt-in', async () => {
      const reports = await client.listReports();
      assert.ok(reports.length > 0, 'derived report list');
      const id = 'camp_20260924_70602bf9';
      const def = await client.getReport(id);
      assert.strictEqual(def.rehydrated, false, 'default is not rehydrated');
      // The extension's ReportContentProvider applies this same net before
      // rendering; after it, no real host/IP survives the default view.
      assert.ok(
        !redact(def.markdown).includes('127.0.0.1'),
        'extension redaction net must mask the target IP in the default view'
      );

      const full = await client.getReport(id, { rehydrate: true });
      assert.strictEqual(full.rehydrated, true);
      assert.ok(full.markdown.includes('127.0.0.1'), 'full report carries real values');
    });
  }
);
