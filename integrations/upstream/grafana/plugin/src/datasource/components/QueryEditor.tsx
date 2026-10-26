import React, { ChangeEvent } from 'react';
import { InlineField, Input, Select, Stack } from '@grafana/ui';
import { QueryEditorProps, SelectableValue } from '@grafana/data';
import { DataSource } from '../datasource';
import { DarkmoonDataSourceOptions, DarkmoonQuery, DarkmoonQueryType } from '../types';

type Props = QueryEditorProps<DataSource, DarkmoonQuery, DarkmoonDataSourceOptions>;

const QUERY_TYPES: Array<SelectableValue<DarkmoonQueryType>> = [
  { label: 'Overview', value: 'overview' },
  { label: 'Campaigns', value: 'campaigns' },
  { label: 'Findings', value: 'findings' },
  { label: 'Targets', value: 'targets' },
  { label: 'Time series', value: 'timeseries' },
  { label: 'Pull requests', value: 'pullrequests' },
  { label: 'Retest', value: 'retest' },
];

export function QueryEditor({ query, onChange, onRunQuery }: Props) {
  const queryType = query.queryType ?? 'overview';

  const set = <K extends keyof DarkmoonQuery>(key: K, value: DarkmoonQuery[K]) => {
    onChange({ ...query, [key]: value });
  };

  const onText =
    (key: keyof DarkmoonQuery) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      set(key, event.target.value as DarkmoonQuery[typeof key]);
    };

  return (
    <Stack direction="column" gap={1}>
      <InlineField label="Query type" labelWidth={16}>
        <Select
          inputId="query-editor-type"
          options={QUERY_TYPES}
          value={queryType}
          width={28}
          onChange={(v) => {
            set('queryType', (v.value as DarkmoonQueryType) ?? 'overview');
            onRunQuery();
          }}
        />
      </InlineField>

      {(queryType === 'findings' || queryType === 'targets') && (
        <Stack gap={1} wrap="wrap">
          {queryType === 'findings' && (
            <>
              <InlineField label="Severity" labelWidth={16}>
                <Input id="q-severity" value={query.severity ?? ''} onChange={onText('severity')} placeholder="critical,high…" width={24} />
              </InlineField>
              <InlineField label="Status" labelWidth={16}>
                <Input id="q-status" value={query.status ?? ''} onChange={onText('status')} width={24} />
              </InlineField>
              <InlineField label="Category" labelWidth={16}>
                <Input id="q-category" value={query.category ?? ''} onChange={onText('category')} width={24} />
              </InlineField>
              <InlineField label="Campaign ID" labelWidth={16}>
                <Input id="q-campaign" value={query.campaign_id ?? ''} onChange={onText('campaign_id')} width={24} />
              </InlineField>
              <InlineField label="Target ID" labelWidth={16}>
                <Input id="q-target" value={query.target_id ?? ''} onChange={onText('target_id')} width={24} />
              </InlineField>
              <InlineField label="Project ID" labelWidth={16}>
                <Input id="q-project" value={query.project_id ?? ''} onChange={onText('project_id')} width={24} />
              </InlineField>
            </>
          )}
          {queryType === 'targets' && (
            <InlineField label="Risk level" labelWidth={16}>
              <Input id="q-risk" value={query.risk_level ?? ''} onChange={onText('risk_level')} width={24} />
            </InlineField>
          )}
        </Stack>
      )}

      {queryType === 'timeseries' && (
        <Stack gap={1} wrap="wrap">
          <InlineField label="Metric" labelWidth={16}>
            <Input id="q-metric" value={query.metric ?? ''} onChange={onText('metric')} placeholder="vulnerabilities_over_time" width={30} />
          </InlineField>
          <InlineField label="Group by" labelWidth={16}>
            <Input id="q-group" value={query.group ?? ''} onChange={onText('group')} placeholder="severity" width={24} />
          </InlineField>
        </Stack>
      )}

      {queryType === 'pullrequests' && (
        <InlineField label="Campaign ID" labelWidth={16}>
          <Input id="q-pr-campaign" value={query.campaign_id ?? ''} onChange={onText('campaign_id')} width={24} />
        </InlineField>
      )}

      {queryType === 'retest' && (
        <InlineField label="Retest ID" labelWidth={16}>
          <Input id="q-retest" value={query.retest_id ?? ''} onChange={onText('retest_id')} onBlur={() => onRunQuery()} width={30} />
        </InlineField>
      )}
    </Stack>
  );
}
