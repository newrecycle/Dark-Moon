import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import * as assert from 'assert';
import Mocha = require('mocha');

/** Executed inside the actual pinned VS Code extension host, not Node Mocha. */
export async function run(): Promise<void> {
  assert.ok(Object.values(os.networkInterfaces()).flat().every(address => address?.internal),
    'Native tests require Docker --network none');
  const progressPath = process.env.DARKMOON_NATIVE_STATUS;
  const progress = { phase: 'starting', passed: 0, failed: 0, started: 0, total: 0 };
  const write = () => {
    // Never persist assertion messages, raw exceptions, stack traces or
    // campaign/finding content. The driver prints this allowlisted JSON only.
    if (progressPath) fs.writeFileSync(progressPath, JSON.stringify(progress) + '\n', { mode: 0o600 });
  };
  write();
  // Node-only data-layer tests run separately, not inside the editor host.
  const mocha = new Mocha({ ui: 'bdd', timeout: 20_000, reporter: 'min', bail: false });
  const root = path.join(__dirname, 'suite');
  for (const name of fs.readdirSync(root).filter(name => name.endsWith('.test.js')).sort()) {
    mocha.addFile(path.join(root, name));
  }
  progress.phase = 'suite_loaded';
  write();
  await new Promise<void>((resolve, reject) => {
    const runner = mocha.run(failures => {
      progress.phase = failures ? 'failed' : 'passed';
      progress.failed = failures;
      write();
      if (failures) reject(new Error('Native extension suite did not pass'));
      else resolve();
    });
    runner.on('start', () => { progress.phase = 'running'; progress.total = runner.total; write(); });
    runner.on('test', () => { progress.started += 1; write(); });
    runner.on('pass', () => { progress.passed += 1; write(); });
    runner.on('fail', () => { progress.failed += 1; write(); });
  });
}
