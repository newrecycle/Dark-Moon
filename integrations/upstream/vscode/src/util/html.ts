import * as vscode from 'vscode';

export function getNonce(): string {
  let text = '';
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let i = 0; i < 32; i++) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}

export function escapeHtml(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Strict CSP for every webview (plan §4):
 *   default-src 'none' — nothing loads unless explicitly allowed
 *   scripts: only our nonce'd bundle from the extension origin
 *   styles: extension origin + a nonce for the theme variables block
 *   img: extension origin + data: (inline severity chips); NO remote images
 *   no connect-src — webviews never talk to the network directly
 */
export function csp(webview: vscode.Webview, nonce: string): string {
  return [
    `default-src 'none'`,
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'nonce-${nonce}'`,
    `script-src 'nonce-${nonce}'`,
    `font-src ${webview.cspSource}`,
  ].join('; ');
}

export function mediaUri(
  webview: vscode.Webview,
  extensionUri: vscode.Uri,
  ...parts: string[]
): vscode.Uri {
  return webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, ...parts));
}
