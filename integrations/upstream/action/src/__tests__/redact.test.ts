import {
  redact,
  registerSecret,
  redactUrlCredentials,
  _clearSecrets,
} from '../redact.js';

describe('redact', () => {
  beforeEach(() => _clearSecrets());

  it('scrubs registered secrets from strings', () => {
    registerSecret('super-secret-token-1234');
    const out = redact('error: token super-secret-token-1234 was rejected');
    expect(out).not.toContain('super-secret-token-1234');
    expect(out).toContain('***');
  });

  it('ignores very short values', () => {
    registerSecret('ab');
    expect(redact('value ab here')).toBe('value ab here');
  });

  it('strips URL credentials', () => {
    expect(redactUrlCredentials('https://user:pass@host/path')).toBe(
      'https://host/path'
    );
    expect(redact('connect to https://admin:hunter2@10.0.0.1:8000/api')).toBe(
      'connect to https://10.0.0.1:8000/api'
    );
  });

  it('handles regex-special characters in secrets', () => {
    registerSecret('a+b(c)[d].e*');
    expect(redact('leak a+b(c)[d].e* end')).toBe('leak *** end');
  });

  it('is a no-op for empty input', () => {
    expect(redact('')).toBe('');
  });
});
