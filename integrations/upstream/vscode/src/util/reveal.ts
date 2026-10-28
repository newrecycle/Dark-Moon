import { randomBytes } from 'crypto';

export interface RevealContext {
  client: object | undefined;
  revision: number;
  allowed: boolean;
}

/** In-memory, resource/client/revision-bound grants. No raw data is retained. */
export class RevealGrants {
  private readonly grants = new Map<string, { id: string; client: object; revision: number; expires: number; timer: ReturnType<typeof setTimeout> }>();

  constructor(
    private readonly context: () => RevealContext,
    private readonly onRevoke: (token: string) => void,
    private readonly ttlMs = 60_000,
    private readonly clock = Date.now
  ) {}

  issue(id: string, expected: RevealContext): string | undefined {
    const current = this.context();
    if (!current.allowed || !current.client || !expected.allowed || current.client !== expected.client || current.revision !== expected.revision) return undefined;
    const token = randomBytes(32).toString('hex');
    this.grants.set(token, { id, client: current.client, revision: current.revision, expires: this.clock() + this.ttlMs, timer: setTimeout(() => this.revoke(token), this.ttlMs) });
    return token;
  }

  valid(token: string, id: string): boolean {
    const grant = this.grants.get(token);
    if (!grant) return false;
    const current = this.context();
    if (!current.allowed || current.client !== grant.client || current.revision !== grant.revision || this.clock() >= grant.expires) {
      this.revoke(token);
      return false;
    }
    return grant.id === id;
  }

  private revoke(token: string): void {
    const grant = this.grants.get(token);
    if (!grant) return;
    clearTimeout(grant.timer);
    this.grants.delete(token);
    this.onRevoke(token);
  }

  invalidate(): void {
    for (const token of [...this.grants.keys()]) this.revoke(token);
  }

  dispose(): void { this.invalidate(); }
}
