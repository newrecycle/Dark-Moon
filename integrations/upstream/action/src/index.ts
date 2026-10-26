import * as core from '@actions/core';
import { run } from './main.js';

run().catch((err: unknown) => {
  // Last-resort guard: main() sets failures internally, but never let an
  // unexpected throw crash the runner without a clear (redaction-safe) message.
  const message = err instanceof Error ? err.message : String(err);
  core.setFailed(`Unexpected error: ${message}`);
});
