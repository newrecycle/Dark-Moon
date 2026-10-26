/**
 * Redaction utilities. The action never prints tokens, licenses, or raw finding
 * evidence to logs or shared surfaces. `core.setSecret()` masks exact values in
 * logs, but we also apply a defense-in-depth redactor for any string we build
 * ourselves (URLs may embed credentials, error messages may echo a token, etc.).
 */

const PLACEHOLDER = '***';

/** Values registered here are scrubbed from any string passed to `redact()`. */
const secrets = new Set<string>();

export function registerSecret(value: string | undefined | null): void {
  if (!value) return;
  const v = String(value).trim();
  if (v.length >= 4) secrets.add(v);
}

/** Remove userinfo (user:pass@) from a URL, keeping scheme+host+path for logs. */
export function redactUrlCredentials(input: string): string {
  return input.replace(/([a-z][a-z0-9+.-]*:\/\/)[^/@\s]*@/gi, '$1');
}

/** Best-effort scrub of registered secrets + URL credentials from a string. */
export function redact(input: string): string {
  if (!input) return input;
  let out = redactUrlCredentials(input);
  for (const s of secrets) {
    if (!s) continue;
    // Escape regex metacharacters in the secret before building the matcher.
    const escaped = s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out.replace(new RegExp(escaped, 'g'), PLACEHOLDER);
  }
  return out;
}

/** For tests / reset. */
export function _clearSecrets(): void {
  secrets.clear();
}
