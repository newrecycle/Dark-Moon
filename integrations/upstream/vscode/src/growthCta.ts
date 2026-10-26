import * as vscode from 'vscode';
import { readSettings } from './config';
import type { SessionData } from './session';

/**
 * Non-intrusive, one-time GitHub star CTA (growth guardrails).
 *
 * Shows a single, dismissible {@link vscode.window.showInformationMessage} the
 * FIRST time Darkmoon delivers real value in VS Code — a successful load with
 * findings, not on activation, not on empty results, not in fixtures/demo mode.
 * It is gated once-only on `globalState` and can be opted out of via the
 * `DARKMOON_DISABLE_GROWTH_CTA` env var or the `darkmoon.growthCta.enabled`
 * setting.
 *
 * Privacy: no target/host/finding data is ever read into the message or stored.
 * `globalState` holds only the boolean flag under {@link STATE_KEY}.
 */
export const STATE_KEY = 'darkmoon.starCtaShown';
export const REPO_URL = 'https://github.com/ASCIT31/Dark-Moon';

const MESSAGE =
  'Darkmoon just delivered your first findings in VS Code. If it is useful, ' +
  'a star on GitHub helps the open source project.';
const STAR = 'Star on GitHub';
const NOT_NOW = 'Not now';

/** True unless opted out via env var or the `darkmoon.growthCta.enabled` setting. */
function ctaEnabled(): boolean {
  if (truthyEnv(process.env.DARKMOON_DISABLE_GROWTH_CTA)) {
    return false;
  }
  return vscode.workspace
    .getConfiguration('darkmoon')
    .get<boolean>('growthCta.enabled', true);
}

function truthyEnv(v: string | undefined): boolean {
  if (!v) {
    return false;
  }
  const s = v.trim().toLowerCase();
  return s !== '' && s !== '0' && s !== 'false' && s !== 'no' && s !== 'off';
}

/** Whether a session update represents the first delivery of real value. */
function isFirstRealValue(data: SessionData): boolean {
  if (data.loading || data.error) {
    return false;
  }
  if (!data.findings || data.findings.length === 0) {
    return false;
  }
  // Demo/fixtures data never counts as real value.
  if (readSettings().useFixtures) {
    return false;
  }
  return true;
}

async function showStarCta(): Promise<void> {
  try {
    const choice = await vscode.window.showInformationMessage(
      MESSAGE,
      STAR,
      NOT_NOW
    );
    if (choice === STAR) {
      await vscode.env.openExternal(vscode.Uri.parse(REPO_URL));
    }
  } catch {
    /* fail-safe: a CTA error must never surface to the user */
  }
}

/** Minimal shape needed from the session; kept narrow so it is easy to test. */
export interface StarCtaSession {
  readonly onDidChange: vscode.Event<SessionData>;
}

/**
 * Subscribe to session updates and show the star CTA at most once, on the first
 * real value. Call this once from `activate()`. Returns the subscription.
 */
export function maybeShowStarCta(
  context: vscode.ExtensionContext,
  session: StarCtaSession
): vscode.Disposable {
  // In-memory guard so rapid successive events cannot double-fire within a
  // single session; `globalState` guarantees once-only across sessions.
  let handled = false;

  const sub = session.onDidChange((data) => {
    try {
      if (handled) {
        return;
      }
      if (context.globalState.get<boolean>(STATE_KEY) === true) {
        handled = true;
        return;
      }
      if (!ctaEnabled()) {
        return;
      }
      if (!isFirstRealValue(data)) {
        return;
      }
      // Mark shown up front so it NEVER repeats, regardless of the button.
      handled = true;
      void context.globalState.update(STATE_KEY, true);
      void showStarCta();
    } catch {
      /* fail-safe: never break the results view */
    }
  });

  context.subscriptions.push(sub);
  return sub;
}
