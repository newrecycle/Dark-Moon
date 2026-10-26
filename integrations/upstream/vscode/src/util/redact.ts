/**
 * Redaction (plan §4 threat model).
 *
 * Reports and findings can carry rehydrated real infrastructure values (IPs,
 * hostnames, URLs, credentials, tokens, JWTs). In a shared/remote editor
 * (Live Share, Remote-SSH, screen share) that is a disclosure risk. The
 * extension therefore renders a REDACTED view by default and only shows
 * rehydrated content on an explicit, local user action.
 *
 * This is a defence-in-depth net on top of the client's own redaction: even if
 * a client returns un-redacted markdown when we asked for redaction, this pass
 * masks the obvious sensitive tokens before anything reaches a webview.
 */

const MASK = '[redacted]';

// Order matters: mask the most specific structures first.
const RULES: Array<{ re: RegExp; replace: string }> = [
  // JWTs (three base64url segments).
  { re: /\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{2,}\b/g, replace: '[redacted-jwt]' },
  // Authorization / bearer / api-key style assignments.
  {
    re: /\b(authorization|bearer|api[-_]?key|x-api-key|token|password|passwd|pwd|secret)\b(\s*[:=]\s*|\s+)("?)[^\s",'}]+\3/gi,
    replace: '$1$2[redacted]',
  },
  // Basic auth / creds embedded in URLs: scheme://user:pass@host
  { re: /([a-z][a-z0-9+.-]*:\/\/)[^\s/@:]+:[^\s/@]+@/gi, replace: '$1[redacted]@' },
  // Private/loopback and generic IPv4 addresses.
  { re: /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g, replace: '[redacted-ip]' },
  // Hostnames with a TLD-ish tail (best effort; keeps common vendor words out).
  {
    re: /\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:local|internal|corp|lan|test|example|com|net|org|io|op)\b/gi,
    replace: '[redacted-host]',
  },
];

export function redact(text: string): string {
  if (!text) {
    return text;
  }
  let out = text;
  for (const rule of RULES) {
    out = out.replace(rule.re, rule.replace);
  }
  return out;
}

/** Redact a Finding for the default (non-rehydrated) detail view. */
export function redactFinding<T>(finding: T): T {
  const walk = (v: unknown): unknown => {
    if (typeof v === 'string') {
      return redact(v);
    }
    if (Array.isArray(v)) {
      return v.map(walk);
    }
    if (v && typeof v === 'object') {
      const o: Record<string, unknown> = {};
      for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
        o[k] = walk(val);
      }
      return o;
    }
    return v;
  };
  return walk(finding) as T;
}

export { MASK };
