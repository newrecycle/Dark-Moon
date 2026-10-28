import * as assert from 'assert';
import * as vscode from 'vscode';
import { ReportContentProvider } from '../../src/views/reportsView';
import { revealContext } from '../../src/util/localReveal';
import { DarkmoonSession } from '../../src/session';
import type { ReportContent } from '../../src/darkmoon/contract';

class SessionFixture {
  readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChange = this.changed.event;
  revision = 1;
  calls = 0;
  client = { getReport: async () => { this.calls++; return { markdown: 'PRIVATE-MNEMONIC-BODY 127.0.0.1', rehydrated: true }; } };
  snapshot = { loading: false, error: undefined, reports: [{ id: 'camp_one' }] };
  capabilities = { rehydratedReports: true };
  getClient() { return this.client; }
  getCampaign(id: string) { return id === 'camp_one' ? { stats: { high: 1 } } : undefined; }
  asSession() { return this as unknown as DarkmoonSession; }
}

describe('Native report provider authorization', () => {
  let fixture: SessionFixture;
  let provider: ReportContentProvider;
  beforeEach(() => {
    fixture = new SessionFixture(); provider = new ReportContentProvider(fixture.asSession(), 1000);
    assert.strictEqual(vscode.workspace.isTrusted, true);
    assert.strictEqual(vscode.env.remoteName, undefined);
    assert.strictEqual(vscode.window.state.focused, true);
  });
  afterEach(() => { provider.dispose(); fixture.changed.dispose(); });
  it('does not fetch a raw body from a forged flag, token or default URI', async () => {
    for (const uri of [ReportContentProvider.uri('camp_one'), ReportContentProvider.uri('camp_one', true), ReportContentProvider.uri('camp_one').with({ query: 'grant=forged' })]) {
      assert.doesNotMatch(await provider.provideTextDocumentContent(uri), /PRIVATE-MNEMONIC|127\.0\.0\.1/);
    }
    assert.strictEqual(fixture.calls, 0);
  });
  it('scopes a confirmed grant to its resource and revokes on refresh', async () => {
    const uri = provider.authorizeFull('camp_one', revealContext(fixture.asSession()))!;
    assert.ok(uri); assert.match(await provider.provideTextDocumentContent(uri), /PRIVATE-MNEMONIC/);
    assert.doesNotMatch(await provider.provideTextDocumentContent(ReportContentProvider.uri('camp_two').with({ query: uri.query })), /PRIVATE-MNEMONIC/);
    fixture.revision++; fixture.changed.fire();
    assert.doesNotMatch(await provider.provideTextDocumentContent(uri), /PRIVATE-MNEMONIC/);
    assert.strictEqual(fixture.calls, 1);
  });
  it('rechecks authorization after a pending read and discards stale full content', async () => {
    let release!: (value: ReportContent) => void;
    fixture.client.getReport = () => new Promise(resolve => { release = resolve; });
    const uri = provider.authorizeFull('camp_one', revealContext(fixture.asSession()))!;
    const pending = provider.provideTextDocumentContent(uri);
    fixture.revision++; fixture.changed.fire();
    release({ markdown: 'PRIVATE-MNEMONIC-BODY', rehydrated: true });
    assert.doesNotMatch(await pending, /PRIVATE-MNEMONIC/);
  });
  it('emits document replacement on expiry and refuses a stale confirmation', async () => {
    provider.dispose(); provider = new ReportContentProvider(fixture.asSession(), 20);
    const expected = revealContext(fixture.asSession());
    const uri = provider.authorizeFull('camp_one', expected)!;
    let replaced = false; provider.onDidChange(value => { if (value.toString() === uri.toString()) replaced = true; });
    await new Promise(resolve => setTimeout(resolve, 60));
    assert.strictEqual(replaced, true); assert.doesNotMatch(await provider.provideTextDocumentContent(uri), /PRIVATE-MNEMONIC/);
    fixture.revision++; assert.strictEqual(provider.authorizeFull('camp_one', expected), undefined);
  });
  it('does not render raw server error strings', async () => {
    fixture.client.getReport = async () => { throw Error('PRIVATE-MNEMONIC-ERROR'); };
    const uri = provider.authorizeFull('camp_one', revealContext(fixture.asSession()))!;
    assert.doesNotMatch(await provider.provideTextDocumentContent(uri), /PRIVATE-MNEMONIC/);
  });
});
