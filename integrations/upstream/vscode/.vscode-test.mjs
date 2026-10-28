import { defineConfig } from '@vscode/test-cli';
import os from 'node:os';
import assert from 'node:assert/strict';
assert.ok(Object.values(os.networkInterfaces()).flat().every(address => address.internal), 'Native editor tests require Docker --network none.');

export default defineConfig({
  label: 'darkmoon',
  files: 'out/test/**/*.test.js',
  version: '1.106.3',
  // Fixture/demo mode so activation loads bundled sample data deterministically.
  launchArgs: ['--disable-extensions'],
  env: {
    DARKMOON_TEST: '1'
  },
  mocha: {
    ui: 'bdd',
    timeout: 60000
  }
});
