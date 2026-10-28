// Bounded, native VS Code 1.106.3 acceptance of the extracted VSIX contents.
// Requires the network-disabled Docker runtime. Does not bypass workspace
// trust, pregrant evidence access, or invoke a real assessment.
'use strict';
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TIMEOUT_MS = 150000;
const EXIT_GRACE_MS = 5000;
const work = path.resolve(__dirname, '../../integrations/upstream/vscode');
const packageRoot = path.resolve('/workspace/vscode-package/extension');
const editor = fs.readFileSync('/opt/vscode-executable', 'utf8').trim();
const session = fs.mkdtempSync(path.join(os.tmpdir(), 'darkmoon-vscode-native-'));
const userData = path.join(session, 'user');
const progressFile = path.join(session, 'native-progress.json');
let child;
let finished = false;
let timedOut = false;
let stdoutBytes = 0;
let stderrBytes = 0;
const stdoutHash = crypto.createHash('sha256');
const stderrHash = crypto.createHash('sha256');
const abort = signal => {
  if (child?.pid) {
    try { process.kill(-child.pid, signal); } catch (e) {
      if (e.code !== 'ESRCH') process.stderr.write('VS Code process-group cleanup unavailable\n');
    }
  }
};
function progress() {
  try {
    const state = JSON.parse(fs.readFileSync(progressFile, 'utf8'));
    return { phase: state.phase, total: state.total, started: state.started,
             passed: state.passed, failed: state.failed,
             failedTests: Array.isArray(state.failedTests) ? state.failedTests.slice(0, 3) : [] };
  } catch { return { phase: 'extension_tests_not_started' }; }
}
function diagnostics(label, code, signal) {
  console.log('native-host diagnostic:', JSON.stringify({
    phase: label, editorVersion: '1.106.3', packaged: true,
    ...progress(), timedOut, exitCode: code, exitSignal: signal,
    stdoutBytes, stderrBytes,
    stdoutSha256: stdoutHash.digest('hex'), stderrSha256: stderrHash.digest('hex')
  }));
}
async function main() {
  assert.ok(Object.values(os.networkInterfaces()).flat().every(n => n?.internal),
    'The actual editor may only run with Docker --network none');
  assert.ok(fs.existsSync(path.join(packageRoot, 'package.json')),
    'Packaged VSIX extension manifest is required');
  assert.ok(fs.existsSync(path.join(packageRoot, 'dist', 'extension.js')),
    'Packaged VSIX extension executable is required');
  fs.mkdirSync(userData, { recursive: true });
  fs.mkdirSync(path.join(session, 'extensions'));
  const settingsDir = path.join(userData, 'User');
  fs.mkdirSync(settingsDir, { recursive: true });
  fs.writeFileSync(path.join(settingsDir, 'settings.json'), JSON.stringify({
    'telemetry.telemetryLevel': 'off', 'update.mode': 'none',
    'extensions.autoCheckUpdates': false, 'extensions.autoUpdate': false,
    'workbench.enableExperiments': false,
    // Keep the real workspace-trust gate enabled. The empty workspace must
    // actually qualify as trusted for positive reveal cases.
    'security.workspace.trust.enabled': true,
    'darkmoon.growthCta.enabled': false,
  }), { mode: 0o600 });
  const args = [
    '--no-sandbox', '--disable-gpu', '--disable-telemetry',
    '--skip-welcome', '--skip-release-notes', '--new-window',
    '--user-data-dir=' + userData,
    '--extensions-dir=' + path.join(session, 'extensions'),
    '--extensionDevelopmentPath=' + packageRoot,
    '--extensionTestsPath=' + path.join(work, 'out/test/nativeRunner.js'),
  ];
  // No --disable-workspace-trust; no --disable-extensions. The isolated
  // extensions directory prevents loading unrelated user extensions.
  console.log('native-host: launching packaged extension under pinned editor');
  const outcome = await new Promise((resolve, reject) => {
    let settled = false;
    const done = result => { if (!settled) { settled = true; resolve(result); } };
    const heartbeat = setInterval(() => console.log(
      'native-host heartbeat: ' + JSON.stringify(progress())), 15000);
    heartbeat.unref();
    child = spawn(editor, args, {
      cwd: work, env: {
        ...process.env, DARKMOON_TEST: '1',
        DARKMOON_DISABLE_GROWTH_CTA: '1',
        DARKMOON_NATIVE_STATUS: progressFile,
        HOME: session,
      }, stdio: ['ignore', 'pipe', 'pipe'], detached: true,
    });
    child.stdout.on('data', chunk => { stdoutBytes += chunk.length; stdoutHash.update(chunk); });
    child.stderr.on('data', chunk => { stderrBytes += chunk.length; stderrHash.update(chunk); });
    const watchdog = setTimeout(() => {
      timedOut = true;
      console.error('native-host: bounded execution deadline reached; last stage ' +
        JSON.stringify(progress()));
      abort('SIGTERM');
      setTimeout(() => {
        abort('SIGKILL');
        // A grandchild can inherit pipe handles after the launcher quits.
        // Terminate the awaiting promise even if 'close' never arrives.
        child.stdout.destroy();
        child.stderr.destroy();
        child.unref();
        done({code: 124, signal: 'WATCHDOG'});
      }, EXIT_GRACE_MS);
    }, TIMEOUT_MS);
    child.once('error', err => {
      clearTimeout(watchdog);
      clearInterval(heartbeat);
      if (!settled) reject(new Error('Unable to start pinned editor (' + (err.code || 'spawn_error') + ')'));
    });
    child.once('close', (code, signal) => {
      clearTimeout(watchdog);
      clearInterval(heartbeat);
      done({ code, signal });
    });
  });
  diagnostics('editor_exited', outcome.code, outcome.signal);
  const result = progress();
  if (timedOut || outcome.code !== 0 || result.phase !== 'passed') {
    throw new Error('Packaged extension-host acceptance did not complete successfully');
  }
  console.log('PASS packaged VS Code 1.106.3 extension host, isolated offline');
}
process.on('SIGTERM', () => abort('SIGTERM'));
process.on('SIGINT', () => abort('SIGTERM'));
main().catch(err => {
  console.error('FAIL VS Code native acceptance: ' + err.message);
  process.exitCode = 1;
}).finally(() => {
  if (!finished) {
    finished = true;
    abort('SIGTERM');
    try { fs.rmSync(session, { recursive: true, force: true }); }
    catch { console.error('Native temporary-state cleanup incomplete'); process.exitCode = 1; }
  }
});
