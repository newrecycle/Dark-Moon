import * as path from 'path';
import type { ClientConfig, CreateClient } from '../src/darkmoon/contract';
import { createFixtureClient } from '../src/darkmoon/fixtureClient';

export const FIXTURES_DIR = path.resolve(__dirname, '..', '..', 'test', 'fixtures');

/** Injectable factory: fixture-backed client whose edition follows cfg.mode. */
export const fakeClientFactory: CreateClient = (cfg: ClientConfig) =>
  createFixtureClient({
    dir: FIXTURES_DIR,
    edition: cfg.mode === 'pro' ? 'pro' : 'oss',
  });
