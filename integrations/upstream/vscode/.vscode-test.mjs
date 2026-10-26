import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
  label: 'darkmoon',
  files: 'out/test/**/*.test.js',
  version: 'stable',
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
