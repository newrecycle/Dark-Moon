// Real fork HTTP/browser deep links with disposable records; no scan or model acceptance.
const { chromium } = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + '/playwright' : 'playwright');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'darkmoon-deep-links-'));
  const child = spawn(process.env.DARKMOON_TEST_PYTHON || 'python3', ['tests/community/browser_fixture.py'], {
    cwd: path.resolve(__dirname, '../..'),
    env: { ...process.env, PYTHONPATH: 'mcp', DARKMOON_SHARED_DIR: root },
  });
  let browser;
  // Fixture diagnostics can contain source paths; do not print them on success.
  child.stderr.on('data', () => {});
  try {
    const fixture = await new Promise((resolve, reject) => {
      let output = '';
      const timer = setTimeout(() => reject(Error('Owned browser fixture startup timeout')), 20000);
      child.stdout.on('data', chunk => {
        output += chunk;
        for (const line of output.split('\n')) {
          try {
            const value = JSON.parse(line);
            if (value.port) { clearTimeout(timer); resolve(value); return; }
          } catch {}
        }
      });
      child.once('exit', code => { clearTimeout(timer); reject(Error('Owned browser fixture exited: ' + code)); });
    });
    const base = 'http://127.0.0.1:' + fixture.port;
    browser = await chromium.launch({ headless: true,
      ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], grants = [], launches = [];
    page.on('pageerror', error => errors.push(error.name));
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname;
      if (request.method() === 'POST' && pathname === '/api/v1/evidence/grants') grants.push(pathname);
      if (request.method() === 'POST' && ['/api/v1/campaigns', '/api/v1/run/campaign'].includes(pathname)) launches.push(pathname);
    });
    async function login(username = 'fixture-admin', password = 'offline-fixture-password') {
      await page.locator('#login[open]').waitFor();
      await page.locator('#login-username').fill(username);
      await page.locator('#token').fill(password);
      await page.locator('#login-form button[type=submit]').click();
      await page.locator('#login').waitFor({ state: 'hidden' });
    }
    const cases = [
      ['/projects', 'Projects & analytics'], ['/history', 'Campaigns'], ['/scheduler', 'Schedules'],
      ['/new-campaign', 'Campaigns'], ['/change-password', 'Settings & accounts'],
      ['/campaign/' + fixture.campaign_id, 'Campaigns'],
      ['/vulnerability/' + fixture.finding_id + '?campaign_id=' + fixture.campaign_id, 'Campaigns'],
      ['/report/' + fixture.campaign_id, 'Campaigns'],
    ];
    for (const [resource, heading] of cases) {
      await page.goto(base + resource);
      assert.equal(await page.locator('[data-revealed-content]').count(), 0);
      await login();
      await page.getByRole('heading', { name: heading, exact: true }).waitFor();
      if (resource === '/new-campaign') await page.locator('#launch-dialog[open]').waitFor();
      if (resource === '/change-password') await page.locator('#workspace-form [name=old_password]').waitFor();
      if (resource.startsWith('/campaign/') || resource.startsWith('/vulnerability/')) {
        await page.locator('#detail[open]').waitFor();
        assert.match(page.url(), new RegExp(fixture.campaign_id));
      }
      if (resource.startsWith('/report/')) await page.getByText('Authorize report preview', { exact: true }).waitFor();
      assert.equal(await page.locator('[data-revealed-content]').count(), 0);
    }
    const loginResponse = await fetch(base + '/api/v1/auth/login', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'fixture-admin', password: 'offline-fixture-password' }) });
    assert.equal(loginResponse.status, 200);
    const admin = await loginResponse.json();
    const created = await fetch(base + '/api/v1/auth/users', { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + admin.token },
      body: JSON.stringify({ username: 'deep-link-viewer', password: 'owned-deep-link-password', role: 'viewer' }) });
    assert.equal(created.status, 201);
    await page.goto(base + '/new-campaign');
    await login('deep-link-viewer', 'owned-deep-link-password');
    await page.getByText('Resource unavailable', { exact: true }).waitFor();
    assert.equal(await page.locator('#launch-dialog[open]').count(), 0);
    assert.deepEqual(launches, []);
    assert.deepEqual(grants, []);
    assert.deepEqual(errors, []);
    console.log('PASS eight authenticated path links, protected content defaults, exact resource scope and viewer launch denial');
  } finally {
    if (browser) await browser.close();
    if (child.exitCode === null) {
      child.kill('SIGTERM');
      await new Promise(resolve => {
        const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
        child.once('exit', () => { clearTimeout(timer); resolve(); });
      });
    }
    await fs.rm(root, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
