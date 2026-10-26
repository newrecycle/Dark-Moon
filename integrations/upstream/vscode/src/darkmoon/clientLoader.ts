/**
 * Client resolution (plan §2.2 consume `@darkmoon/client`; do NOT reimplement).
 *
 * Resolution order:
 *   1. A test/factory injection (setClientFactory) — used by integration tests.
 *   2. Fixture/demo mode (`darkmoon.dev.useFixtures` or DARKMOON_FIXTURES env)
 *      — a static demo data source so the packaged .vsix is smoke-testable
 *      before the real package is linkable.
 *   3. The real `@darkmoon/client` package (production data path).
 *   4. An "unavailable" client that surfaces a friendly install hint.
 *
 * Nothing here reimplements the OSS-CLI or Pro-REST adapters; those live in
 * `@darkmoon/client`.
 */
import type {
  ClientConfig,
  CreateClient,
  DarkmoonClient,
} from './contract';
import { fixtureClientFromConfig } from './fixtureClient';
import { createRealClient } from './realAdapter';

export interface LoaderContext {
  /** Absolute path to the bundled demo fixtures (extensionUri/resources/fixtures). */
  fixturesDir: string;
  /** True when `darkmoon.dev.useFixtures` is enabled. */
  useFixtures: boolean;
}

let injectedFactory: CreateClient | undefined;

/** Test seam: integration tests inject a client factory here. */
export function setClientFactory(factory: CreateClient | undefined): void {
  injectedFactory = factory;
}

class UnavailableClient implements DarkmoonClient {
  constructor(private readonly reason: string) {}
  private fail(): never {
    throw new Error(this.reason);
  }
  async capabilities() {
    return this.fail();
  }
  async listCampaigns() {
    return this.fail();
  }
  async getCampaign() {
    return this.fail();
  }
  async listFindings() {
    return this.fail();
  }
  async getFinding() {
    return this.fail();
  }
  async listReports() {
    return this.fail();
  }
  async getReport() {
    return this.fail();
  }
  async launchCampaign() {
    return this.fail();
  }
}

export async function resolveClient(
  cfg: ClientConfig,
  ctx: LoaderContext
): Promise<DarkmoonClient> {
  if (injectedFactory) {
    return injectedFactory(cfg);
  }
  if (ctx.useFixtures) {
    return fixtureClientFromConfig(cfg, ctx.fixturesDir);
  }
  // `@darkmoon/client` is bundled into the extension. createRealClient throws
  // synchronously only if the package could not be loaded at all — degrade
  // gracefully to a friendly, actionable state instead of failing activation.
  try {
    return createRealClient(cfg);
  } catch (err) {
    return new UnavailableClient(
      'Darkmoon client could not be initialised: ' +
        (err instanceof Error ? err.message : String(err)) +
        '. Enable "darkmoon.dev.useFixtures" for a demo.'
    );
  }
}
