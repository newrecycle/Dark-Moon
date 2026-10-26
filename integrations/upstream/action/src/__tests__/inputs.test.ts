import { readInputs } from '../inputs.js';

function setInput(name: string, value: string): void {
  process.env[`INPUT_${name.toUpperCase()}`] = value;
}
function clearInputs(): void {
  for (const k of Object.keys(process.env)) if (k.startsWith('INPUT_')) delete process.env[k];
}

describe('readInputs', () => {
  beforeEach(() => {
    clearInputs();
    setInput('safe-harbor', 'false');
    setInput('post-report', 'false');
    setInput('full-report', 'false');
  });
  afterAll(() => clearInputs());

  it('throws when no transport is configured (auto)', () => {
    setInput('target', 'x');
    expect(() => readInputs()).toThrow(/base-url.*OSS|oss-data-dir/);
  });

  it('throws when no target/targets', () => {
    setInput('base-url', 'https://dm.example.com');
    expect(() => readInputs()).toThrow(/No target/);
  });

  it('builds Pro client config from base-url + api-token', () => {
    setInput('base-url', 'https://dm.example.com');
    setInput('api-token', 'jwt-token-value');
    setInput('target', 'http://127.0.0.1:3000');
    const i = readInputs();
    expect(i.clientConfig.pro?.baseUrl).toBe('https://dm.example.com');
    expect(i.clientConfig.pro?.token).toBe('jwt-token-value');
    expect(i.clientConfig.pro?.refuseInsecureDefault).toBe(true);
    expect(i.secretsToMask).toContain('jwt-token-value');
  });

  it('builds OSS client config from oss-data-dir', () => {
    setInput('mode', 'oss');
    setInput('oss-data-dir', '/data/darkmoon-settings');
    setInput('oss-reports-dir', '/data/reports');
    setInput('target', 'http://127.0.0.1:3000');
    const i = readInputs();
    expect(i.mode).toBe('oss');
    expect(i.clientConfig.oss?.dataDir).toBe('/data/darkmoon-settings');
    expect(i.clientConfig.oss?.reportsDir).toBe('/data/reports');
  });

  it('requires oss-data-dir when mode=oss', () => {
    setInput('mode', 'oss');
    setInput('target', 'x');
    expect(() => readInputs()).toThrow(/oss-data-dir/);
  });

  it('parses launch DSL fields and fail-on string', () => {
    setInput('base-url', 'https://dm.example.com');
    setInput('target', 'http://127.0.0.1:3000');
    setInput('focus', 'sqli, xss ,idor');
    setInput('exclude', 'dom-xss\nclickjacking');
    setInput('out-of-scope', '10.0.0.0/8');
    setInput('rules', 'POC only; no real data');
    setInput('fail-on', 'critical,high');
    const i = readInputs();
    expect(i.launch.focus).toEqual(['sqli', 'xss', 'idor']);
    expect(i.launch.exclude).toEqual(['dom-xss', 'clickjacking']);
    expect(i.launch.outOfScope).toEqual(['10.0.0.0/8']);
    expect(i.launch.rules).toEqual(['POC only', 'no real data']);
    expect(i.failOn).toBe('critical,high');
  });

  it('refuse-insecure-default can be disabled', () => {
    setInput('base-url', 'https://dm.example.com');
    setInput('target', 'x');
    setInput('refuse-insecure-default', 'false');
    const i = readInputs();
    expect(i.clientConfig.pro?.refuseInsecureDefault).toBe(false);
  });

  it('defaults mode auto, report-format markdown, post-report false', () => {
    setInput('base-url', 'https://dm.example.com');
    setInput('target', 'x');
    const i = readInputs();
    expect(i.mode).toBe('auto');
    expect(i.reportFormat).toBe('markdown');
    expect(i.postReport).toBe(false);
  });
});
