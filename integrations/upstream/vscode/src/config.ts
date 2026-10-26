import * as vscode from 'vscode';
import type { ClientConfig } from './darkmoon/contract';

export interface ExtensionSettings {
  mode: 'oss' | 'pro' | 'auto';
  baseUrl?: string;
  dataDir?: string;
  cliPath?: string;
  useFixtures: boolean;
  redactByDefault: boolean;
}

export function readSettings(): ExtensionSettings {
  const cfg = vscode.workspace.getConfiguration('darkmoon');
  return {
    mode: cfg.get<'oss' | 'pro' | 'auto'>('mode', 'auto'),
    baseUrl: emptyToUndef(cfg.get<string>('baseUrl', '')),
    dataDir: emptyToUndef(cfg.get<string>('dataDir', '')),
    cliPath: emptyToUndef(cfg.get<string>('cliPath', '')),
    useFixtures: cfg.get<boolean>('dev.useFixtures', false),
    redactByDefault: cfg.get<boolean>('reports.redactByDefault', true),
  };
}

/** Build the ClientConfig, injecting secrets (never read from settings). */
export function toClientConfig(
  settings: ExtensionSettings,
  secrets: { token?: string; license?: string }
): ClientConfig {
  return {
    mode: settings.mode,
    baseUrl: settings.baseUrl,
    dataDir: settings.dataDir,
    cliPath: settings.cliPath,
    token: secrets.token,
    license: secrets.license,
  };
}

/**
 * Warn if a Pro base URL is non-HTTPS and not loopback (secrets would travel
 * in clear). Returns a warning string or undefined.
 */
export function baseUrlWarning(baseUrl?: string): string | undefined {
  if (!baseUrl) {
    return undefined;
  }
  let u: URL;
  try {
    u = new URL(baseUrl);
  } catch {
    return `Darkmoon base URL is not a valid URL: ${baseUrl}`;
  }
  const loopback = ['localhost', '127.0.0.1', '::1'].includes(u.hostname);
  if (u.protocol !== 'https:' && !loopback) {
    return `Darkmoon base URL uses ${u.protocol} — credentials would be sent unencrypted. Use https.`;
  }
  return undefined;
}

function emptyToUndef(v: string | undefined): string | undefined {
  return v && v.trim() ? v.trim() : undefined;
}
