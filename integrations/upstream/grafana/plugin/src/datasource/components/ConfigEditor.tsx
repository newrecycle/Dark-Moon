import React, { ChangeEvent } from 'react';
import { InlineField, Input, SecretInput, Select } from '@grafana/ui';
import { DataSourcePluginOptionsEditorProps, SelectableValue } from '@grafana/data';
import { DarkmoonDataSourceOptions, DarkmoonSecureJsonData } from '../types';

interface Props extends DataSourcePluginOptionsEditorProps<DarkmoonDataSourceOptions, DarkmoonSecureJsonData> {}

const MODE_OPTIONS: Array<SelectableValue<string>> = [
  { label: 'Auto-detect', value: 'auto' },
  { label: 'OSS / Community', value: 'oss' },
  { label: 'Pro', value: 'pro' },
];

export function ConfigEditor(props: Props) {
  const { onOptionsChange, options } = props;
  const { jsonData, secureJsonFields, secureJsonData } = options;

  const onBaseUrlChange = (event: ChangeEvent<HTMLInputElement>) => {
    onOptionsChange({ ...options, jsonData: { ...jsonData, baseUrl: event.target.value } });
  };

  const onModeChange = (v: SelectableValue<string>) => {
    onOptionsChange({ ...options, jsonData: { ...jsonData, mode: (v.value as 'auto' | 'oss' | 'pro') ?? 'auto' } });
  };

  const onTokenChange = (event: ChangeEvent<HTMLInputElement>) => {
    onOptionsChange({ ...options, secureJsonData: { darkmoonToken: event.target.value } });
  };

  const onResetToken = () => {
    onOptionsChange({
      ...options,
      secureJsonFields: { ...options.secureJsonFields, darkmoonToken: false },
      secureJsonData: { ...options.secureJsonData, darkmoonToken: '' },
    });
  };

  return (
    <>
      <InlineField label="Base URL" labelWidth={18} interactive tooltip={'Darkmoon API base URL, e.g. https://darkmoon.example.com'}>
        <Input
          id="config-editor-base-url"
          onChange={onBaseUrlChange}
          value={jsonData.baseUrl}
          placeholder="https://darkmoon.example.com"
          width={48}
        />
      </InlineField>
      <InlineField label="Mode" labelWidth={18} interactive tooltip={'auto detects the edition from the API; force OSS or Pro if needed'}>
        <Select
          inputId="config-editor-mode"
          options={MODE_OPTIONS}
          value={jsonData.mode ?? 'auto'}
          onChange={onModeChange}
          width={48}
        />
      </InlineField>
      <InlineField label="API token" labelWidth={18} interactive tooltip={'Pro bearer token / JWT. Stored encrypted and only sent to the backend.'}>
        <SecretInput
          id="config-editor-token"
          isConfigured={secureJsonFields?.darkmoonToken}
          value={secureJsonData?.darkmoonToken}
          placeholder="Bearer token (leave empty for OSS)"
          width={48}
          onReset={onResetToken}
          onChange={onTokenChange}
        />
      </InlineField>
    </>
  );
}
