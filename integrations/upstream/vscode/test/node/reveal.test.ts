import * as assert from 'assert';
import { RevealGrants, type RevealContext } from '../../src/util/reveal';

describe('Reveal grants', () => {
  let context: RevealContext;
  let clock: number;
  let revoked: string[];
  let grants: RevealGrants;
  beforeEach(() => {
    context = { client: {}, revision: 1, allowed: true };
    clock = 1000; revoked = [];
    grants = new RevealGrants(() => context, token => revoked.push(token), 60_000, () => clock);
  });
  afterEach(() => grants.dispose());
  it('rejects forged tokens and binds a grant to one resource', () => {
    assert.strictEqual(grants.valid('rehydrate=1', 'one'), false);
    const token = grants.issue('one', { ...context })!;
    assert.match(token, /^[a-f0-9]{64}$/);
    assert.strictEqual(grants.valid(token, 'two'), false);
    assert.strictEqual(grants.valid(token, 'one'), true);
  });
  it('expires exactly at the deadline and never revives', () => {
    const token = grants.issue('one', { ...context })!;
    clock += 59_999; assert.strictEqual(grants.valid(token, 'one'), true);
    clock++; assert.strictEqual(grants.valid(token, 'one'), false);
    clock = 1000; assert.strictEqual(grants.valid(token, 'one'), false);
    assert.deepStrictEqual(revoked, [token]);
  });
  it('rejects confirmation captured before a refresh or client replacement', () => {
    const expected = { ...context };
    context.revision++; assert.strictEqual(grants.issue('one', expected), undefined);
    context = { ...expected, client: {} }; assert.strictEqual(grants.issue('one', expected), undefined);
  });
  it('revokes on refresh, credential change, focus/trust/remote ineligibility', () => {
    for (const mutate of [() => context.revision++, () => { context.client = {}; }, () => { context.allowed = false; }]) {
      context = { client: {}, revision: 1, allowed: true };
      const token = grants.issue('one', { ...context })!; mutate();
      assert.strictEqual(grants.valid(token, 'one'), false);
      context.allowed = true; assert.strictEqual(grants.valid(token, 'one'), false);
    }
  });
  it('explicit invalidation clears all outstanding resources', () => {
    const one = grants.issue('one', { ...context })!, two = grants.issue('two', { ...context })!;
    grants.invalidate(); assert.deepStrictEqual(revoked, [one, two]);
    assert.strictEqual(grants.valid(one, 'one'), false);
  });
  it('refuses grants while the policy is unavailable', () => {
    context.allowed = false; assert.strictEqual(grants.issue('one', context), undefined);
    context.allowed = true; assert.strictEqual(grants.issue('one', { ...context, allowed: false }), undefined);
    context.client = undefined; assert.strictEqual(grants.issue('one', context), undefined);
  });
  it('fires active expiry so a displayed full document can be replaced', async () => {
    grants.dispose(); grants = new RevealGrants(() => context, token => revoked.push(token), 10);
    const token = grants.issue('one', context)!;
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.deepStrictEqual(revoked, [token]); assert.strictEqual(grants.valid(token, 'one'), false);
  });
});
