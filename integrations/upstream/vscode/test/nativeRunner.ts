import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import * as assert from 'assert';
import Mocha = require('mocha');

export async function run(): Promise<void> {
  assert.ok(Object.values(os.networkInterfaces()).flat().every(address => address?.internal), 'Native tests require Docker --network none');
  const mocha = new Mocha({ ui: 'bdd', timeout: 60_000 });
  for (const directory of ['node', 'suite']) {
    const root = path.join(__dirname, directory);
    for (const name of fs.readdirSync(root).filter(name => name.endsWith('.test.js')).sort()) mocha.addFile(path.join(root, name));
  }
  await new Promise<void>((resolve, reject) => mocha.run(failures => failures ? reject(Error(`${failures} native extension tests failed`)) : resolve()));
}
