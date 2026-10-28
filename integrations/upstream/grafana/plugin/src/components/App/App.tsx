import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppRootProps } from '@grafana/data';
import { PLUGIN_BASE_URL } from '../../constants';
import DatasourceView, { VIEWS } from '../DatasourceView';

export default function App(props: AppRootProps) {
  const settings = props.meta.jsonData as { datasourceUid?: string } | undefined;
  return <Routes>
    {VIEWS.map(view => <Route key={view.type} path={view.type} element={<DatasourceView type={view.type} defaultUid={settings?.datasourceUid} />} />)}
    <Route path="*" element={<Navigate to={`${PLUGIN_BASE_URL}/overview`} replace />} />
  </Routes>;
}
