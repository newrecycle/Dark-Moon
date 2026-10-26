import * as assert from 'assert';
import * as vscode from 'vscode';
import { maybeShowStarCta, STATE_KEY, REPO_URL } from '../../src/growthCta';
import type { SessionData } from '../../src/session';

const STAR = 'Star on GitHub';

/** In-memory ExtensionContext stub — only what maybeShowStarCta touches. */
function fakeContext(
  initial: Record<string, unknown> = {}
): vscode.ExtensionContext {
  const store = new Map<string, unknown>(Object.entries(initial));
  const globalState = {
    get: (k: string, d?: unknown) => (store.has(k) ? store.get(k) : d),
    update: async (k: string, v: unknown) => {
      store.set(k, v);
    },
    keys: () => Array.from(store.keys()),
    setKeysForSync: () => {
      /* noop */
    },
  };
  return {
    subscriptions: [] as vscode.Disposable[],
    globalState,
  } as unknown as vscode.ExtensionContext;
}

function loaded(
  findingCount: number,
  extra: Partial<SessionData> = {}
): SessionData {
  return {
    campaigns: [],
    findings: Array.from(
      { length: findingCount },
      (_, i) => ({ id: `f${i}` } as unknown as SessionData['findings'][number])
    ),
    reports: [],
    loading: false,
    error: undefined,
    ...extra,
  };
}

// --- window.showInformationMessage / env.openExternal stubs ---
let calls: string[] = [];
let opened: string[] = [];
let originalShow: typeof vscode.window.showInformationMessage;
let originalOpen: typeof vscode.env.openExternal;

function installStubs(choice?: string): void {
  calls = [];
  opened = [];
  originalShow = vscode.window.showInformationMessage;
  originalOpen = vscode.env.openExternal;
  (vscode.window as { showInformationMessage: unknown }).showInformationMessage =
    (msg: string) => {
      calls.push(msg);
      return Promise.resolve(choice);
    };
  Object.defineProperty(vscode.env, 'openExternal', {
    configurable: true,
    value: (uri: vscode.Uri) => {
      opened.push(uri.toString());
      return Promise.resolve(true);
    },
  });
}

function restoreStubs(): void {
  (vscode.window as { showInformationMessage: unknown }).showInformationMessage =
    originalShow;
  Object.defineProperty(vscode.env, 'openExternal', {
    configurable: true,
    value: originalOpen,
  });
}

async function setConfig(key: string, value: unknown): Promise<void> {
  await vscode.workspace
    .getConfiguration('darkmoon')
    .update(key, value, vscode.ConfigurationTarget.Global);
}

/** Let the async button handler settle. */
const flush = () => new Promise((r) => setImmediate(r));

describe('Growth star CTA (guardrails)', () => {
  beforeEach(() => installStubs('Not now'));

  afterEach(async () => {
    restoreStubs();
    delete process.env.DARKMOON_DISABLE_GROWTH_CTA;
    await setConfig('growthCta.enabled', undefined);
    await setConfig('dev.useFixtures', undefined);
  });

  it('shows once on first real value and never again', async () => {
    const ctx = fakeContext();
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(3));
    assert.strictEqual(calls.length, 1, 'CTA shows on first findings');
    assert.strictEqual(
      ctx.globalState.get(STATE_KEY),
      true,
      'flag persisted regardless of button'
    );

    emitter.fire(loaded(3));
    assert.strictEqual(calls.length, 1, 'CTA does not repeat on a second refresh');
  });

  it('does not show on activation / empty / loading / error states', async () => {
    const ctx = fakeContext();
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(0)); // empty results
    emitter.fire({ ...loaded(3), loading: true }); // still loading
    emitter.fire({ ...loaded(3), error: 'boom' }); // failed load
    assert.strictEqual(calls.length, 0, 'no CTA without real value');
  });

  it('does not show in fixtures / demo mode', async () => {
    await setConfig('dev.useFixtures', true);
    const ctx = fakeContext();
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(3));
    assert.strictEqual(calls.length, 0, 'fixtures mode is not real value');
  });

  it('does not show when disabled by setting', async () => {
    await setConfig('growthCta.enabled', false);
    const ctx = fakeContext();
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(3));
    assert.strictEqual(calls.length, 0, 'setting opt-out honored');
  });

  it('does not show when disabled by env var', async () => {
    process.env.DARKMOON_DISABLE_GROWTH_CTA = '1';
    const ctx = fakeContext();
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(3));
    assert.strictEqual(calls.length, 0, 'env opt-out honored');
  });

  it('does not show when globalState flag is already set', async () => {
    const ctx = fakeContext({ [STATE_KEY]: true });
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(3));
    assert.strictEqual(calls.length, 0, 'already-shown flag respected');
  });

  it('opens the GitHub repo when "Star on GitHub" is chosen', async () => {
    restoreStubs();
    installStubs(STAR);
    const ctx = fakeContext();
    const emitter = new vscode.EventEmitter<SessionData>();
    maybeShowStarCta(ctx, { onDidChange: emitter.event });

    emitter.fire(loaded(3));
    await flush();
    assert.strictEqual(calls.length, 1);
    assert.ok(
      opened.includes(REPO_URL),
      `expected openExternal(${REPO_URL}), got ${JSON.stringify(opened)}`
    );
  });
});
