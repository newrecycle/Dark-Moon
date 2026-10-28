import * as vscode from 'vscode';
import type { DarkmoonSession } from '../session';
import type { RevealContext } from './reveal';

export function revealContext(session: DarkmoonSession): RevealContext {
  return {
    client: session.getClient(),
    revision: session.revision,
    allowed: !vscode.env.remoteName && vscode.workspace.isTrusted && vscode.window.state.focused && !session.snapshot.loading && !session.snapshot.error && session.capabilities?.rehydratedReports === true,
  };
}
