'use strict';
// Native Splunk Web / SplunkJS verification. No browser SDK mocks on the
// successful paths. Mocked HTTP failures are labelled fault injection.
// Requires a disposable, operator-authorized loopback Splunk Web session.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const crypto = require('node:crypto');

function loopback(raw, allowHttp = true) {
  const u = new URL(raw);
  assert.ok(['127.0.0.1', '[::1]', '::1'].includes(u.hostname), 'browser requires loopback Web/fixture');
  assert.ok(['https:', ...(allowHttp ? ['http:'] : [])].includes(u.protocol));
  assert.ok(!u.username && !u.password && !u.search && !u.hash);
  return u.origin;
}

async function inspect(page, endpoint, data = {}) {
  return page.evaluate(({ endpoint, data }) => new Promise((resolve, reject) => {
    require(['splunkjs/mvc'], mvc => {
      const service = mvc.createService({ owner: 'nobody', app: 'darkmoon' });
      service.get(endpoint, data, (error, response) => {
        if (error) return reject(new Error('native SplunkJS endpoint failed'));
        resolve(response && response.data);
      });
    }, () => reject(new Error('native SplunkJS module unavailable')));
  }), { endpoint, data });
}

function one(data) {
  assert.equal(data?.entry?.length, 1, 'native SplunkJS must return one settings entry');
  return data.entry[0].content;
}

async function bound(page) {
  const settings = one(await inspect(page, 'configs/conf-darkmoon/settings'));
  const realm = settings.credential_realm;
  assert.match(realm, /^darkmoon-[0-9a-f]{32}$/, 'native settings must select immutable generation');
  const rows = (await inspect(page, 'storage/passwords', { count: 0 }))?.entry;
  assert.ok(Array.isArray(rows), 'native encrypted credential listing unavailable');
  const matching = rows.filter(x => x.content?.username === 'darkmoon' && x.content?.realm === realm);
  assert.equal(matching.length, 1, 'native credential realm lookup ambiguous or missing');
  assert.ok(matching[0].content?.clear_password, 'native lookup did not return a usable test secret');
  return { realm, base_url: settings.base_url, token: matching[0].content.clear_password };
}

async function setup(page, web, user, pass) {
  await page.goto(web + '/en-US/app/darkmoon/darkmoon_setup', { waitUntil: 'domcontentloaded' });
  const username = page.locator('input[name=username]');
  if (await username.count()) {
    await username.first().fill(user);
    await page.locator('input[name=password]').first().fill(pass);
    await page.locator('button[type=submit], input[type=submit]').first().click();
  }
  await page.locator('#dm_save').waitFor({ state: 'visible', timeout: 25000 });
  await page.waitForFunction(() => !document.querySelector('#dm_save').disabled,
    { timeout: 25000 });
}

async function save(page, base, token) {
  await page.locator('#dm_base_url').fill(base);
  await page.locator('#dm_verify_tls').selectOption('0');
  await page.locator('#dm_token').fill(token);
  await page.locator('#dm_save').click();
  await page.waitForFunction(() => /saved|confirmed|could not|unavailable/i.test(
    document.querySelector('#dm_status')?.textContent || ''), { timeout: 20000 });
  return await page.locator('#dm_status').textContent();
}

async function main() {
  if (process.env.SPLUNK_NATIVE_ATTESTED !== '1') {
    process.stderr.write('NATIVE UNAVAILABLE: operator authorization missing\n');
    process.exitCode = 3; return;
  }
  const mandatory = ['SPLUNK_NATIVE_WEB', 'SPLUNK_NATIVE_USER',
    'SPLUNK_NATIVE_PASSWORD', 'SPLUNK_NATIVE_DARKMOON'];
  const absent = mandatory.filter(name => !process.env[name]);
  if (absent.length) {
    process.stderr.write('NATIVE UNAVAILABLE: ' + absent.join(', ') + ' missing\n');
    process.exitCode = 3; return;
  }
  const web = loopback(process.env.SPLUNK_NATIVE_WEB);
  const fixture = loopback(process.env.SPLUNK_NATIVE_DARKMOON);
  const original = 'fixture-darkmoon-token';
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ ignoreHTTPSErrors: process.env.SPLUNK_NATIVE_INSECURE_LOOPBACK === '1' });
    // Native browser tests are never allowed to reach external services,
    // including CDN redirects or third-party alert destinations.
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (['http:', 'https:'].includes(url.protocol) &&
          !['127.0.0.1', '[::1]', '::1'].includes(url.hostname)) {
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    await setup(page, web, process.env.SPLUNK_NATIVE_USER, process.env.SPLUNK_NATIVE_PASSWORD);

    const result = await save(page, fixture, original);
    assert.match(result, /Configuration saved|Connection saved/);
    const first = await bound(page);
    assert.equal(first.base_url, fixture);
    assert.equal(first.token, original);
    console.log('PASS native SplunkJS create/lookup and settings-to-realm binding');

    // Failed password creation must not point settings at an uncreated secret.
    let failureSeen = false;
    await page.route(/storage\/passwords/, async route => {
      if (route.request().method() !== 'POST') return route.continue();
      failureSeen = true;
      return route.fulfill({ status: 503, body: '{"error":"fixture refusal"}',
        contentType: 'application/json' });
    });
    const rejected = await save(page, fixture, 'fixture-rejected-' + crypto.randomUUID());
    assert.equal(failureSeen, true, 'native storage/passwords request not observed');
    assert.match(rejected, /credential could not be confirmed/i);
    const afterFailure = await bound(page);
    assert.deepEqual(afterFailure, first, 'failed native credential creation changed selected generation');
    await page.unroute(/storage\/passwords/);
    console.log('PASS native SplunkJS failed create preserves prior URL and realm');

    // Two native pages are independent clients. Each new token gets a unique
    // generation; whichever stanza write wins must select its OWN token.
    const a = await context.newPage(), b = await context.newPage();
    await Promise.all([setup(a, web, process.env.SPLUNK_NATIVE_USER, process.env.SPLUNK_NATIVE_PASSWORD),
                       setup(b, web, process.env.SPLUNK_NATIVE_USER, process.env.SPLUNK_NATIVE_PASSWORD)]);
    const tokenA = 'fixture-concurrent-A-' + crypto.randomUUID();
    const tokenB = 'fixture-concurrent-B-' + crypto.randomUUID();
    await Promise.all([save(a, fixture, tokenA), save(b, fixture, tokenB)]);
    const selected = await bound(page);
    assert.ok([tokenA, tokenB].includes(selected.token), 'concurrent saves selected a foreign token');
    assert.equal(selected.base_url, fixture);
    assert.notEqual(selected.realm, first.realm);
    console.log('PASS concurrent native SplunkJS saves preserve URL/token generation');

    // The initial token remains stored, not silently overwritten or deleted.
    const passwords = (await inspect(page, 'storage/passwords', { count: 0 })).entry;
    assert.equal(passwords.filter(x => x.content?.realm === first.realm &&
      x.content?.clear_password === original).length, 1);
    console.log('PASS old credential generation survives native concurrent rotation');
    // Restore the owned fixture token so the installed alert action can safely
    // exercise its own real management/password lookup against this host.
    const restored = await save(page, fixture, original);
    assert.match(restored, /Configuration saved|Connection saved/);
    assert.equal((await bound(page)).token, original);

    // Native dashboard and alert form availability, without enabling alerts.
    await page.goto(web + '/en-US/app/darkmoon/darkmoon_findings');
    await page.getByText(/Latest observed finding state within the selected time range/i).waitFor({ timeout: 20000 });
    const dashboard = await inspect(page, 'data/ui/views/darkmoon_findings');
    assert.equal(dashboard.entry.length, 1);
    const action = await inspect(page, 'alerts/alert_actions/darkmoon_campaign');
    assert.equal(action.entry.length, 1);
    console.log('PASS native dashboard and alert registration');
    console.log('NATIVE WEB/SplunkJS PASS');
  } catch (error) {
    // Do not print URLs, request contents, session keys or password values.
    process.stderr.write('NATIVE WEB FAIL: ' + (error instanceof assert.AssertionError ?
      error.message.replace(/fixture-[\w-]+/g, '[redacted]') :
      error.name || 'browser error') + '\n');
    process.exitCode = 1;
  } finally {
    await browser?.close();
  }
}
main().catch(() => {
  process.stderr.write('NATIVE WEB FAIL: unexpected browser error\n');
  process.exitCode = 1;
});
