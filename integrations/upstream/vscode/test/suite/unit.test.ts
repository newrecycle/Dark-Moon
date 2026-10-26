import * as assert from 'assert';
import { redact, redactFinding } from '../../src/util/redact';
import { compareFindings } from '../../src/util/severity';
import { baseUrlWarning } from '../../src/config';
import { SEVERITY_ORDER, type Finding } from '../../src/darkmoon/contract';

function mkFinding(p: Partial<Finding>): Finding {
  return {
    id: p.id ?? 'v',
    campaign_id: 'c',
    title: p.title ?? 't',
    severity: p.severity ?? 'low',
    status: p.status ?? 'confirmed',
    description: p.description ?? '',
    cvss_score: p.cvss_score,
    ...p,
  } as Finding;
}

describe('redaction (plan §4)', () => {
  it('masks IPv4 addresses', () => {
    assert.ok(!redact('host 192.168.56.10 down').includes('192.168.56.10'));
    assert.match(redact('192.168.56.10'), /redacted-ip/);
  });
  it('masks JWTs', () => {
    const jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEF_123-xyz';
    assert.ok(!redact(`token ${jwt}`).includes(jwt));
  });
  it('masks credentials in URLs', () => {
    assert.ok(!redact('http://admin:s3cret@box/').includes('s3cret'));
  });
  it('masks password/token assignments', () => {
    assert.ok(!redact('password: hunter2').includes('hunter2'));
    assert.ok(!redact('Authorization: Bearer abc123def').includes('abc123def'));
  });
  it('masks internal hostnames', () => {
    assert.match(redact('dc10.evilcorp.local'), /redacted-host/);
  });
  it('recursively redacts a finding object', () => {
    const f = mkFinding({
      description: 'reachable at 10.0.0.5',
      evidence: { raw_response: 'pw=topsecret' } as Finding['evidence'],
    });
    const r = redactFinding(f);
    assert.ok(!JSON.stringify(r).includes('10.0.0.5'));
    assert.ok(!JSON.stringify(r).includes('topsecret'));
    // Non-sensitive fields survive.
    assert.strictEqual(r.severity, 'low');
  });
});

describe('severity ordering', () => {
  it('orders critical < high < medium < low < info', () => {
    assert.ok(SEVERITY_ORDER.critical < SEVERITY_ORDER.high);
    assert.ok(SEVERITY_ORDER.high < SEVERITY_ORDER.medium);
    assert.ok(SEVERITY_ORDER.low < SEVERITY_ORDER.info);
  });
  it('sorts findings by severity then cvss', () => {
    const findings = [
      mkFinding({ id: 'a', severity: 'low', cvss_score: 3 }),
      mkFinding({ id: 'b', severity: 'critical', cvss_score: 9 }),
      mkFinding({ id: 'c', severity: 'high', cvss_score: 8 }),
      mkFinding({ id: 'd', severity: 'high', cvss_score: 9.5 }),
    ].sort(compareFindings);
    assert.deepStrictEqual(
      findings.map((f) => f.id),
      ['b', 'd', 'c', 'a']
    );
  });
});

describe('baseUrl warning (plan §4)', () => {
  it('warns on plain http to a remote host', () => {
    assert.ok(baseUrlWarning('http://darkmoon.example.com'));
  });
  it('allows https', () => {
    assert.strictEqual(baseUrlWarning('https://darkmoon.example.com'), undefined);
  });
  it('allows http to localhost', () => {
    assert.strictEqual(baseUrlWarning('http://localhost:8080'), undefined);
  });
  it('flags an invalid url', () => {
    assert.ok(baseUrlWarning('not a url'));
  });
});
