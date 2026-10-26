import * as vscode from 'vscode';

/**
 * Secrets live ONLY in SecretStorage (plan §4). They are never written to
 * settings.json, never logged, and never placed in a webview.
 */
export const SECRET_TOKEN = 'darkmoon.pro.token';
export const SECRET_LICENSE = 'darkmoon.license';

export class SecretsStore {
  constructor(private readonly secrets: vscode.SecretStorage) {}

  async read(): Promise<{ token?: string; license?: string }> {
    const [token, license] = await Promise.all([
      this.secrets.get(SECRET_TOKEN),
      this.secrets.get(SECRET_LICENSE),
    ]);
    return { token: token || undefined, license: license || undefined };
  }

  get onDidChange(): vscode.Event<vscode.SecretStorageChangeEvent> {
    return this.secrets.onDidChange;
  }

  async setToken(): Promise<boolean> {
    const value = await vscode.window.showInputBox({
      title: 'Darkmoon Pro — API token',
      prompt: 'Bearer token for the Darkmoon Pro REST API. Stored in the OS secret store.',
      password: true,
      ignoreFocusOut: true,
    });
    if (value === undefined) {
      return false;
    }
    if (value.trim() === '') {
      await this.secrets.delete(SECRET_TOKEN);
    } else {
      await this.secrets.store(SECRET_TOKEN, value.trim());
    }
    return true;
  }

  async setLicense(): Promise<boolean> {
    const value = await vscode.window.showInputBox({
      title: 'Darkmoon — License key',
      prompt: 'Darkmoon license key. Stored in the OS secret store.',
      password: true,
      ignoreFocusOut: true,
    });
    if (value === undefined) {
      return false;
    }
    if (value.trim() === '') {
      await this.secrets.delete(SECRET_LICENSE);
    } else {
      await this.secrets.store(SECRET_LICENSE, value.trim());
    }
    return true;
  }

  async clearAll(): Promise<void> {
    await Promise.all([
      this.secrets.delete(SECRET_TOKEN),
      this.secrets.delete(SECRET_LICENSE),
    ]);
  }
}
