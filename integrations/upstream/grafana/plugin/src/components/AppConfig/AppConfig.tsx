import React, { FormEvent, useState } from 'react';
import { AppPluginMeta, PluginConfigPageProps } from '@grafana/data';
import { getBackendSrv } from '@grafana/runtime';
import { useDarkmoonSources } from '../DatasourceView';

type AppSettings = { datasourceUid?: string };
export interface AppConfigProps extends PluginConfigPageProps<AppPluginMeta<AppSettings>> {}

export default function AppConfig({ plugin }: AppConfigProps) {
  const { sources, error, loading } = useDarkmoonSources();
  const [uid, setUid] = useState(plugin.meta.jsonData?.datasourceUid || '');
  const [status, setStatus] = useState('');
  const [saving, setSaving] = useState(false);
  function save(event: FormEvent) {
    event.preventDefault();
    if (!sources.some(source => source.uid === uid)) { return; }
    setSaving(true); setStatus('');
    getBackendSrv().fetch({ url: `/api/plugins/${plugin.meta.id}/settings`, method: 'POST', data: {
      enabled: plugin.meta.enabled, pinned: plugin.meta.pinned, jsonData: { datasourceUid: uid },
    } }).subscribe({ next: () => { setSaving(false); setStatus('Saved. Reopen the Darkmoon app to use this default datasource.'); },
      error: () => { setSaving(false); setStatus('Configuration could not be saved with this Grafana account.'); } });
  }
  return <form onSubmit={save}>
    <h2>Darkmoon datasource</h2>
    <p>Configure the API URL and token on a Darkmoon Security Posture datasource. Its backend reads the encrypted token; this app does not store a second copy.</p>
    <a href="/connections/datasources">Manage datasources</a>
    {loading && <p>Loading configured datasources…</p>}{error && <p role="alert">{error}</p>}
    <p><label>Default datasource <select value={uid} onChange={event => setUid(event.target.value)}>
      <option value="">Select a datasource</option>{sources.map(source => <option key={source.uid} value={source.uid}>{source.name}</option>)}
    </select></label></p>
    <button type="submit" disabled={saving || !sources.some(source => source.uid === uid)}>Save datasource selection</button>
    {status && <p role="status">{status}</p>}
  </form>;
}
