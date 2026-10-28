import React, { useEffect, useMemo, useState } from 'react';
import { getBackendSrv, PluginPage } from '@grafana/runtime';
import { DarkmoonQueryType } from '../datasource/types';
import { PLUGIN_BASE_URL } from '../constants';

export const DATASOURCE_TYPE = 'darkmoon-securityposture-datasource';
export type Source = { uid: string; name: string; type: string };
type Frame = { schema: { name?: string; fields: Array<{ name: string }> }; data: { values: unknown[][] } };
type QueryResponse = { results: Record<string, { error?: string; frames?: Frame[] }> };

function validFrames(value: unknown): value is Frame[] {
  return Array.isArray(value) && value.every(frame => {
    if (!frame || !Array.isArray(frame.schema?.fields) || !Array.isArray(frame.data?.values)) { return false; }
    if (frame.schema.name !== undefined && typeof frame.schema.name !== 'string') { return false; }
    const fields: unknown[] = frame.schema.fields;
    const columns: unknown[] = frame.data.values;
    if (fields.length !== columns.length || !fields.every(field => typeof (field as { name?: unknown } | null)?.name === 'string')) { return false; }
    const rows = Array.isArray(columns[0]) ? columns[0].length : 0;
    return columns.every(column => Array.isArray(column) && column.length === rows);
  });
}
export const VIEWS: Array<{ type: DarkmoonQueryType; label: string }> = [
  { type: 'overview', label: 'Overview' }, { type: 'campaigns', label: 'Campaigns' },
  { type: 'findings', label: 'Findings' }, { type: 'targets', label: 'Targets' },
  { type: 'timeseries', label: 'Trends' }, { type: 'pullrequests', label: 'Published PRs' },
  { type: 'remediation', label: 'Local proposals' }, { type: 'retest', label: 'Retests' },
];

export function useDarkmoonSources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    const subscription = getBackendSrv().fetch<Source[]>({ url: '/api/datasources', method: 'GET' }).subscribe({
      next: response => {
        if (!active) { return; }
        if (!Array.isArray(response.data) || response.data.some(source => !source || typeof source.type !== 'string' || typeof source.uid !== 'string' || typeof source.name !== 'string')) { setError('Datasource configuration could not be read.'); setLoading(false); return; }
        setSources(response.data.filter(source => source.type === DATASOURCE_TYPE && typeof source.uid === 'string'));
        setLoading(false);
      },
      error: () => { if (active) { setError('Datasource configuration could not be read with this Grafana account.'); setLoading(false); } },
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);
  return { sources, error, loading };
}

function cell(value: unknown): string {
  if (value === null || value === undefined) { return 'Unavailable'; }
  if (typeof value === 'string' || typeof value === 'boolean') { return String(value); }
  if (typeof value === 'number' && Number.isFinite(value)) { return String(value); }
  return 'Unavailable';
}

export default function DatasourceView({ type, defaultUid }: { type: DarkmoonQueryType; defaultUid?: string }) {
  const { sources, error: sourceError, loading: sourcesLoading } = useDarkmoonSources();
  const [selected, setSelected] = useState(() => new URLSearchParams(window.location.search).get('datasource') || '');
  const [campaign, setCampaign] = useState('');
  const [severity, setSeverity] = useState('');
  const [retest, setRetest] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const configured = defaultUid ? sources.some(source => source.uid === defaultUid) ? defaultUid : '' : sources.length === 1 ? sources[0].uid : '';
  // An explicit, inaccessible UID must fail closed, never fall back to a different configured datasource.
  const uid = selected ? (sources.some(source => source.uid === selected) ? selected : '') : configured;
  const unavailableSelection = !sourcesLoading && !sourceError && !!(selected || defaultUid) && !uid;
  const query = useMemo(() => ({ refId: 'A', datasource: { uid, type: DATASOURCE_TYPE }, queryType: type,
    ...(['findings', 'pullrequests', 'remediation'].includes(type) && campaign ? { campaign_id: campaign } : {}), ...(type === 'findings' && severity ? { severity } : {}),
    ...(type === 'timeseries' ? { metric: 'severity', group: 'day' } : {}),
    ...(type === 'retest' ? { retest_id: retest } : {}),
  }), [uid, type, campaign, severity, retest]);

  useEffect(() => {
    setFrames([]); setError(''); setLoaded(false); setLoading(false);
    if (!uid || type === 'retest' && !retest) { return; }
    let active = true;
    setLoading(true);
    const now = Date.now();
    const subscription = getBackendSrv().fetch<QueryResponse>({ url: '/api/ds/query', method: 'POST', data: {
      queries: [{ ...query, ...(type === 'timeseries' ? { params: { from: new Date(now - 30 * 86400000).toISOString(), to: new Date(now).toISOString() } } : {}) }], from: String(now - 30 * 86400000), to: String(now),
    } }).subscribe({
      next: response => {
        if (!active) { return; }
        const result = response.data?.results?.A;
        if (!result || result.error || !validFrames(result.frames)) {
          setError('This read did not return a valid result. Check datasource access and the API contract.');
        } else { setFrames(result.frames); setLoaded(true); }
        setLoading(false);
      },
      error: () => { if (active) { setError('The datasource read failed. This does not establish an empty or clean assessment.'); setLoading(false); } },
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, [uid, type, retest, query, refresh]);

  const title = VIEWS.find(view => view.type === type)?.label || 'Darkmoon';
  return <PluginPage><section style={{ maxWidth: 1400 }}>
    <h1>Darkmoon · {title}</h1>
    <nav aria-label="Darkmoon views" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 24 }}>
      {VIEWS.map(view => <a key={view.type} href={`${PLUGIN_BASE_URL}/${view.type}${uid ? `?datasource=${encodeURIComponent(uid)}` : ''}`}>{view.label}</a>)}
    </nav>
    <p>Reads use the configured Grafana datasource and its encrypted credentials. Raw evidence and report bodies are excluded.</p>
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 24 }}>
      <label>Datasource <select value={uid} onChange={event => setSelected(event.target.value)}>
        <option value="">Select a Darkmoon datasource</option>
        {sources.map(source => <option value={source.uid} key={source.uid}>{source.name}</option>)}
      </select></label>
      {['findings', 'pullrequests', 'remediation'].includes(type) && <label>Campaign ID <input value={campaign} onChange={event => setCampaign(event.target.value.trim())} /></label>}
      {type === 'findings' && <label>Severity <select value={severity} onChange={event => setSeverity(event.target.value)}>
        <option value="">All severities</option>{['critical', 'high', 'medium', 'low', 'info'].map(value => <option key={value}>{value}</option>)}
      </select></label>}
      {type === 'retest' && <label>Retest ID <input value={retest} onChange={event => setRetest(event.target.value.trim())} /></label>}
      <button type="button" disabled={!uid || loading} onClick={() => setRefresh(value => value + 1)}>Refresh</button>
      <a href="/connections/datasources">Configure datasource</a>
    </div>
    {sourcesLoading && <p role="status">Loading datasource configuration…</p>}
    {sourceError && <p role="alert">{sourceError}</p>}
    {unavailableSelection && <p role="alert">The selected datasource is unavailable to this account. Choose an accessible datasource.</p>}
    {!sourcesLoading && !sourceError && sources.length === 0 && <p>Add a Darkmoon Security Posture datasource, configure its API URL and token, then use Save &amp; test.</p>}
    {type === 'retest' && !retest && <p>Enter a saved retest ID to read its current status and findings. This page does not launch an assessment.</p>}
    {loading && <p role="status">Reading current metadata…</p>}
    {error && <p role="alert">{error}</p>}
    {loaded && !frames.some(frame => (frame.data.values[0]?.length || 0) > 0) && <p>The API returned no rows for this view. This alone does not establish assessment success.</p>}
    {frames.map((frame, frameIndex) => <section key={frameIndex} style={{ marginBottom: 24 }}>
      <h2>{frame.schema.name || title}</h2>
      <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead><tr>{frame.schema.fields.map((field, index) => <th style={{ textAlign: 'left', padding: 8 }} key={index}>{field.name}</th>)}</tr></thead>
        <tbody>{Array.from({ length: Math.min(frame.data.values[0]?.length || 0, 500) }, (_, row) => <tr key={row}>
          {frame.schema.fields.map((_, column) => <td style={{ padding: 8, verticalAlign: 'top', overflowWrap: 'anywhere' }} key={column}>{cell(frame.data.values[column]?.[row])}</td>)}
        </tr>)}</tbody>
      </table></div>
      {(frame.data.values[0]?.length || 0) > 500 && <p>Showing 500 rows. Refine the filters or use this datasource in Explore for the complete result.</p>}
    </section>)}
    {type === 'overview' && <p>Counts describe retained records. Local proposal validation does not establish deployment or a published fix.</p>}
    {type === 'retest' && <p>Verdicts are reported by the producer. A finding marked not_observed is not proof of a deployed fix or a successful exploit retest.</p>}
  </section></PluginPage>;
}
