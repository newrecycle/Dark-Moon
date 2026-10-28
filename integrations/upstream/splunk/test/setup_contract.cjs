'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../darkmoon/appserver/static/setup.js'), 'utf8');
const originalRealm = 'darkmoon-' + 'a'.repeat(32);
const clone = value => JSON.parse(JSON.stringify(value));
function state() {
  return { settings: { base_url: 'https://old.invalid', verify_tls: '1', credential_realm: originalRealm },
    secrets: new Map([[originalRealm, 'old-fixture-secret']]) };
}
function page(shared = state(), options = {}) {
  const elements = new Map(), calls = [];
  function $(selector) {
    if (!elements.has(selector)) {
      elements.set(selector, { value: '', properties: {}, handlers: {}, content: '',
        val(value) { if (!arguments.length) return this.value; this.value = value; return this; },
        prop(key, value) { if (arguments.length === 1) return this.properties[key]; this.properties[key] = value; return this; },
        text(value) { this.content = value; return this; },
        removeClass() { return this; }, addClass() { return this; },
        on(event, callback) { this.handlers[event] = callback; return this; }
      });
    }
    return elements.get(selector);
  }
  const service = {
    get(endpoint, data, callback) { calls.push({ kind: 'get', endpoint, data, callback }); },
    post(endpoint, data, callback) { calls.push({ kind: endpoint === 'configs/conf-darkmoon/settings' ? 'settings' : 'mark', endpoint, data: clone(data), callback }); },
    storagePasswords(scope) {
      assert.deepEqual(clone(scope), { owner: 'nobody', app: 'darkmoon' });
      return { create(data, callback) { calls.push({ kind: 'credential', data: clone(data), callback }); } };
    }
  };
  vm.runInNewContext(source, {
    URL, Uint8Array, window: { crypto: options.crypto === false ? undefined : webcrypto },
    require(dependencies, factory) { factory($, { createService(scope) {
      assert.deepEqual(clone(scope), { owner: 'nobody', app: 'darkmoon' });
      return service;
    } }); }
  }, { filename: 'setup.js' });
  function reply(call, error = null, apply = false) {
    if (call.kind === 'get') {
      call.callback(error, { data: { entry: [{ content: clone(shared.settings) }] } });
      return;
    }
    if (!error || apply) {
      if (call.kind === 'credential') {
        assert.equal(call.data.name, 'darkmoon');
        assert(!shared.secrets.has(call.data.realm), 'A credential generation must never be overwritten');
        shared.secrets.set(call.data.realm, call.data.password);
      }
      if (call.kind === 'settings') shared.settings = clone(call.data);
    }
    call.callback(error);
  }
  if (options.load !== false) reply(calls[0]);
  return { $, calls, shared, reply,
    click(values = {}) { for (const [id, value] of Object.entries(values)) $('#' + id).val(value); $('#dm_save').handlers.click(); },
    writes() { return calls.filter(call => call.kind !== 'get'); },
    status() { return $('#dm_status').content; },
    next(kind) { return calls.findLast(call => call.kind === kind); }
  };
}

test('stores a new generation before switching connection settings; old secret is retained', () => {
  const p = page();
  p.click({ dm_base_url: 'https://new.invalid', dm_token: 'new-fixture-secret' });
  assert.deepEqual(p.writes().map(c => c.kind), ['credential']);
  const credential = p.next('credential');
  assert.match(credential.data.realm, /^darkmoon-[0-9a-f]{32}$/);
  assert.notEqual(credential.data.realm, originalRealm);
  assert.equal(p.shared.settings.base_url, 'https://old.invalid');
  p.reply(credential);
  assert.equal(p.shared.secrets.get(originalRealm), 'old-fixture-secret');
  assert.equal(p.next('settings').data.credential_realm, credential.data.realm);
  p.reply(p.next('settings'));
  p.reply(p.next('mark'));
  assert.equal(p.shared.settings.base_url, 'https://new.invalid');
  assert.equal(p.shared.secrets.get(p.shared.settings.credential_realm), 'new-fixture-secret');
  assert.equal(p.$('#dm_token').value, '');
  assert.equal(p.$('#dm_save').properties.disabled, false);
});

test('a failed credential save cannot repoint or overwrite the old connection', () => {
  const p = page();
  p.click({ dm_base_url: 'https://new.invalid', dm_token: 'PRIVATE-new' });
  p.reply(p.next('credential'), new Error('PRIVATE-server-error'));
  assert.equal(p.writes().some(c => c.kind === 'settings'), false);
  assert.equal(p.shared.settings.credential_realm, originalRealm);
  assert.equal(p.shared.secrets.get(originalRealm), 'old-fixture-secret');
  assert.doesNotMatch(p.status(), /PRIVATE/);
});

for (const applied of [false, true]) test(`uncertain settings result remains reference-safe (server applied=${applied})`, () => {
  const p = page();
  p.click({ dm_base_url: 'https://new.invalid', dm_token: 'new-fixture-secret' });
  p.reply(p.next('credential'));
  p.reply(p.next('settings'), new Error('PRIVATE-network-error'), applied);
  assert.equal(p.$('#dm_save').properties.disabled, true);
  const reference = p.shared.settings.credential_realm;
  assert.equal(p.shared.secrets.get(reference), applied ? 'new-fixture-secret' : 'old-fixture-secret');
  assert.equal(p.shared.secrets.get(originalRealm), 'old-fixture-secret');
  assert.doesNotMatch(p.status(), /PRIVATE/);
});

test('one page serializes repeated clicks while a save is in flight', () => {
  const p = page();
  p.click({ dm_token: 'new-fixture-secret' });
  p.click({ dm_token: 'different-fixture-secret' });
  assert.equal(p.writes().length, 1);
  assert.equal(p.next('credential').data.password, 'new-fixture-secret');
});

test('two pages retain correct URL/token pairings and old in-flight readers', () => {
  const shared = state(), a = page(shared), b = page(shared);
  a.click({ dm_base_url: 'https://a.invalid', dm_token: 'token-a' });
  b.click({ dm_base_url: 'https://b.invalid', dm_token: 'token-b' });
  a.reply(a.next('credential')); b.reply(b.next('credential'));
  assert.notEqual(a.next('credential').data.realm, b.next('credential').data.realm);
  assert.equal(shared.secrets.get(originalRealm), 'old-fixture-secret');
  b.reply(b.next('settings')); a.reply(a.next('settings'));
  assert.equal(shared.settings.base_url, 'https://a.invalid');
  assert.equal(shared.secrets.get(shared.settings.credential_realm), 'token-a');
  assert.equal(shared.secrets.get(b.next('credential').data.realm), 'token-b');
});

test('blank token is allowed only for the same normalized base URL', () => {
  const p = page();
  p.click({ dm_base_url: 'https://new.invalid' });
  assert.equal(p.writes().length, 0);
  p.click({ dm_base_url: 'https://old.invalid/' });
  assert.equal(p.next('settings').data.credential_realm, originalRealm);
  assert.equal(p.writes().some(c => c.kind === 'credential'), false);
});

test('legacy empty-realm token is preserved on same-connection saves', () => {
  const shared = state(); shared.settings.credential_realm = '';
  const p = page(shared); p.click();
  assert.equal(p.next('settings').data.credential_realm, '');
});

test('initialization failure or malformed settings do not permit blind saves', () => {
  for (const response of [null, { data: { entry: [null] } }, { data: { entry: [] } },
      { data: { entry: [{ content: { credential_realm: false } }] } },
      { data: { entry: [{ content: { verify_tls: 'maybe' } }] } }]) {
    const p = page(state(), { load: false });
    p.calls[0].callback(null, response); p.click({ dm_token: 'fixture-token' });
    assert.equal(p.writes().length, 0);
    assert.equal(p.$('#dm_save').properties.disabled, true);
  }
});

test('cannot save before settings load or without secure random generation', () => {
  const p = page(state(), { load: false }); p.click({ dm_token: 'new-fixture-secret' });
  assert.equal(p.writes().length, 0);
  const q = page(state(), { crypto: false }); q.click({ dm_token: 'new-fixture-secret' });
  assert.equal(q.writes().length, 0);
  assert.equal(q.$('#dm_save').properties.disabled, false);
});

test('invalid service URLs and token headers are rejected before any write', () => {
  for (const url of ['http://new.invalid', 'https://u:p@new.invalid', 'https://new.invalid/?', 'https://new.invalid/#',
      'https://new.invalid:0', 'https://new.invalid\\other', 'https://new.invalid/a b']) {
    const p = page(); p.click({ dm_base_url: url, dm_token: 'fixture-token' });
    assert.equal(p.writes().length, 0, url);
  }
  for (const token of [' padded ', 'line\nheader', 'x'.repeat(16385)]) {
    const p = page(); p.click({ dm_token: token }); assert.equal(p.writes().length, 0);
  }
});

test('HTTP requires explicit lab mode and legacy false flags are respected', () => {
  const p = page(); p.click({ dm_base_url: 'http://owned.invalid', dm_verify_tls: '0', dm_token: 'fixture-token' });
  assert.equal(p.writes().length, 1);
  const shared = state(); shared.settings.verify_tls = 'false';
  assert.equal(page(shared).$('#dm_verify_tls').value, '0');
});

test('setup-marker failure does not conceal that the connection was saved', () => {
  const p = page(); p.click(); p.reply(p.next('settings')); p.reply(p.next('mark'), new Error('PRIVATE'));
  assert.match(p.status(), /Connection saved/);
  assert.doesNotMatch(p.status(), /PRIVATE/);
  assert.equal(p.$('#dm_save').properties.disabled, false);
});
