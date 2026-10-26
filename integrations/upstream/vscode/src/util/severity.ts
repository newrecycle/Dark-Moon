import * as vscode from 'vscode';
import { SEVERITY_ORDER, type Finding, type Severity } from '../darkmoon/contract';

const SEV_ICON: Record<Severity, string> = {
  critical: 'error',
  high: 'flame',
  medium: 'warning',
  low: 'info',
  info: 'circle-small',
};

const SEV_THEME_COLOR: Record<Severity, string> = {
  critical: 'charts.red',
  high: 'charts.orange',
  medium: 'charts.yellow',
  low: 'charts.blue',
  info: 'charts.foreground',
};

export function severityIcon(sev: Severity): vscode.ThemeIcon {
  return new vscode.ThemeIcon(
    SEV_ICON[sev] ?? 'circle-small',
    new vscode.ThemeColor(SEV_THEME_COLOR[sev] ?? 'charts.foreground')
  );
}

export function compareFindings(a: Finding, b: Finding): number {
  const s =
    (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99);
  if (s !== 0) {
    return s;
  }
  const av = a.cvss_score ?? -1;
  const bv = b.cvss_score ?? -1;
  if (av !== bv) {
    return bv - av;
  }
  return a.title.localeCompare(b.title);
}

export function severityRank(sev: Severity): number {
  return SEVERITY_ORDER[sev] ?? 99;
}
