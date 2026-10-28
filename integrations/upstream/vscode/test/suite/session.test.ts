import * as assert from 'assert';
import * as vscode from 'vscode';
import { DarkmoonSession } from '../../src/session';
import { setClientFactory } from '../../src/darkmoon/clientLoader';
import { fakeClientFactory } from '../fakeClient';
import { SecretsStore } from '../../src/secrets';
import type { ClientConfig, DarkmoonClient } from '../../src/darkmoon/contract';

describe('Native session refresh boundaries', () => {
  afterEach(() => setClientFactory(undefined));
  const create = () => new DarkmoonSession({ extensionUri: vscode.Uri.file(__dirname) } as vscode.ExtensionContext, { read: async () => ({}) } as unknown as SecretsStore);
  it('a failed refresh removes the previous client, capabilities and sensitive snapshot', async () => {
    const session = create();
    try {
      setClientFactory(fakeClientFactory); await session.refresh(); assert.ok(session.snapshot.findings.length);
      setClientFactory(() => { throw Error('PRIVATE-AUTH-ERROR'); }); await session.refresh();
      assert.strictEqual(session.getClient(), undefined); assert.strictEqual(session.capabilities, undefined);
      assert.deepStrictEqual(session.snapshot.findings, []); assert.doesNotMatch(session.snapshot.error!, /PRIVATE-AUTH/);
    } finally { session.dispose(); }
  });
  it('an older pending refresh cannot replace a newer session', async () => {
    const session = create();
    let release!: (client: DarkmoonClient) => void;
    let firstStarted!: () => void;
    const started = new Promise<void>(resolve => { firstStarted = resolve; });
    const config: ClientConfig = { mode: 'oss' };
    const first = await fakeClientFactory(config), second = await fakeClientFactory(config);
    let staleReads = 0, disposed = false;
    first.capabilities = async () => { staleReads++; throw Error('stale client should not read'); };
    first.dispose = () => { disposed = true; };
    try {
      setClientFactory(() => { firstStarted(); return new Promise(resolve => { release = resolve; }); });
      const pending = session.refresh(); await started;
      setClientFactory(() => second); await session.refresh();
      assert.strictEqual(session.getClient(), second);
      release(first); await pending;
      assert.strictEqual(session.getClient(), second); assert.strictEqual(staleReads, 0); assert.strictEqual(disposed, true);
    } finally { session.dispose(); }
  });
});
