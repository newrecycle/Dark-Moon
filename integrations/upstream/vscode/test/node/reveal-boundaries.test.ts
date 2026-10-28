import * as assert from 'assert';
import { RevealGrants, type RevealContext } from '../../src/util/reveal';

describe('Reveal grant isolation: focus, selection, connection, credential, expiry', () => {
  const original = {};
  const replacement = {};
  const selected = { client: original, revision: 4, allowed: true };
  let current: RevealContext;
  let revoked: string[];
  let clock: number;
  let grants: RevealGrants;

  beforeEach(() => {
    current = { ...selected }; revoked = []; clock = 1000;
    grants = new RevealGrants(() => current, token => { revoked.push(token); },
      1000, () => clock);
  });
  afterEach(() => grants.dispose());

  it('allows only exact resource and current client', () => {
    const token = grants.issue('campaign_alpha', selected)!;
    assert.ok(token && token.length > 40);
    assert.strictEqual(grants.valid(token, 'campaign_alpha'), true);
    assert.strictEqual(grants.valid(token, 'campaign_beta'), false);
    assert.strictEqual(grants.valid('forged', 'campaign_alpha'), false);
    assert.strictEqual(revoked.length, 0);
  });
  it('revokes on workbench focus or trust loss', () => {
    const token = grants.issue('finding_alpha', selected)!;
    current = { ...current, allowed: false };
    assert.strictEqual(grants.valid(token, 'finding_alpha'), false);
    current = { ...current, allowed: true };
    assert.strictEqual(grants.valid(token, 'finding_alpha'), false);
    assert.deepStrictEqual(revoked, [token]);
  });
  it('revokes on selection/credential/connection revision or client change', () => {
    for (const changed of [
      {client: original, revision: 5, allowed: true},
      {client: replacement, revision: 4, allowed: true},
    ]) {
      const token = grants.issue('finding', { ...current })!;
      current = changed;
      assert.strictEqual(grants.valid(token, 'finding'), false);
      assert.ok(revoked.includes(token));
      current = { ...selected };
    }
  });
  it('rejects a stale approval after revision or focus changed', () => {
    current = { ...selected, revision: 5 };
    assert.strictEqual(grants.issue('finding', selected), undefined);
    current = { ...selected, allowed: false };
    assert.strictEqual(grants.issue('finding', selected), undefined);
  });
  it('expires before full content is accessible and invalidates subscriptions', () => {
    const token = grants.issue('report', selected)!;
    clock += 1000;
    assert.strictEqual(grants.valid(token, 'report'), false);
    assert.deepStrictEqual(revoked, [token]);
    const another = grants.issue('report', { ...current })!;
    grants.invalidate();
    assert.ok(revoked.includes(another));
    assert.strictEqual(grants.valid(another, 'report'), false);
  });
});
