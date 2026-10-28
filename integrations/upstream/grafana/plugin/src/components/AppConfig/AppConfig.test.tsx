import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { of } from 'rxjs';
import AppConfig, { AppConfigProps } from './AppConfig';
import { getBackendSrv } from '@grafana/runtime';

jest.mock('../DatasourceView', () => ({
  useDarkmoonSources: () => ({
    sources: [{ uid: 'darkmoon-1', name: 'Offline datasource', type: 'darkmoon-securityposture-datasource' }],
    loading: false,
    error: '',
  }),
}));
jest.mock('@grafana/runtime', () => ({ getBackendSrv: jest.fn() }));

const fetch = jest.fn();
beforeEach(() => {
  fetch.mockReset();
  fetch.mockReturnValue(of({ data: {} }));
  (getBackendSrv as jest.Mock).mockReturnValue({ fetch });
});

const props = {
  plugin: {
    meta: { id: 'darkmoon-securityposture-app', enabled: true, pinned: false,
      jsonData: {}, name: 'Darkmoon Security Posture' },
  },
  query: {},
} as unknown as AppConfigProps;

test('stores only a datasource UID, not base URL or credentials', async () => {
  render(<AppConfig {...props} />);
  expect(screen.getByText(/configure the API URL and token on a Darkmoon Security Posture datasource/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /save datasource selection/i })).toBeDisabled();
  fireEvent.change(screen.getByRole('combobox', { name: /default datasource/i }), { target: { value: 'darkmoon-1' } });
  fireEvent.click(screen.getByRole('button', { name: /save datasource selection/i }));
  await waitFor(() => expect(screen.getByText(/saved. reopen the darkmoon app/i)).toBeInTheDocument());
  const call = fetch.mock.calls[0][0];
  expect(call.url).toEqual('/api/plugins/darkmoon-securityposture-app/settings');
  expect(call.data.jsonData).toEqual({ datasourceUid: 'darkmoon-1' });
  expect(JSON.stringify(call.data)).not.toMatch(/token|baseUrl|password|secret/i);
});
