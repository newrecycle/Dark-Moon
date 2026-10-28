import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { of, Subject } from 'rxjs';
import { getBackendSrv } from '@grafana/runtime';
import DatasourceView from './DatasourceView';

jest.mock('@grafana/runtime', () => ({
  getBackendSrv: jest.fn(),
  PluginPage: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

const sources = [{ uid: 'darkmoon-1', name: 'Offline Darkmoon', type: 'darkmoon-securityposture-datasource' }];
const stateFrame = (status: string) => ({
  schema: { name: 'retest_state', fields: [
    { name: 'retest_id' }, { name: 'status' }, { name: 'base_campaign_id' },
    { name: 'new_campaign_id' }, { name: 'target_id' }, { name: 'run_id' },
  ] },
  data: { values: [['retest_1'], [status], ['campaign_before'],
    ['campaign_after'], ['target_1'], ['run_1']] },
});
const comparisonFrame = () => ({
  schema: { name: 'retest', fields: [{ name: 'finding_id' }, { name: 'verdict' }] },
  data: { values: [[], []] },
});
const response = (frames: unknown[]) => ({ data: { results: { A: { frames } } } });
const fetch = jest.fn();

beforeEach(() => {
  fetch.mockReset();
  window.history.replaceState({}, '', '/');
  (getBackendSrv as jest.Mock).mockReturnValue({ fetch });
});

test('explicitly unavailable UID fails closed instead of using configured default', async () => {
  window.history.replaceState({}, '', '/?datasource=unavailable');
  fetch.mockReturnValue(of({ data: sources }));
  render(<DatasourceView type="overview" defaultUid="darkmoon-1" />);
  expect(await screen.findByText(/selected datasource is unavailable/i)).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([r]) => r.url === '/api/ds/query')).toHaveLength(0);
});

test('malformed or unequal frame columns produce error, not a clean empty result', async () => {
  fetch.mockImplementation((request) => request.url === '/api/datasources'
    ? of({ data: sources })
    : of(response([{ schema: { name: 'malformed', fields: [{ name: 'one' }, { name: 'two' }] },
      data: { values: [['a', 'b'], ['only-one']] } }])));
  render(<DatasourceView type="overview" defaultUid="darkmoon-1" />);
  expect(await screen.findByText(/did not return a valid result/i)).toBeInTheDocument();
  expect(screen.queryByText(/API returned no rows/i)).not.toBeInTheDocument();
});

test('retains running lifecycle when verdict comparison frame has zero rows', async () => {
  fetch.mockImplementation((request) => request.url === '/api/datasources'
    ? of({ data: sources }) : of(response([stateFrame('running'), comparisonFrame()])));
  render(<DatasourceView type="retest" defaultUid="darkmoon-1" />);
  fireEvent.change(screen.getByRole('textbox', { name: /retest id/i }), { target: { value: 'retest_1' } });
  expect(await screen.findByText('retest_state')).toBeInTheDocument();
  expect(screen.getByText('running')).toBeInTheDocument();
  expect(screen.getByText('campaign_before')).toBeInTheDocument();
  expect(screen.getByText('campaign_after')).toBeInTheDocument();
  expect(screen.getByText('target_1')).toBeInTheDocument();
  expect(screen.getByText('run_1')).toBeInTheDocument();
  expect(screen.getByText(/not proof of a deployed fix/i)).toBeInTheDocument();
});

test('stale asynchronous results cannot replace a newer selected retest', async () => {
  const requests: Array<Subject<unknown>> = [];
  fetch.mockImplementation((request) => {
    if (request.url === '/api/datasources') { return of({ data: sources }); }
    const subject = new Subject<unknown>();
    requests.push(subject);
    return subject;
  });
  render(<DatasourceView type="retest" defaultUid="darkmoon-1" />);
  const input = screen.getByRole('textbox', { name: /retest id/i });
  fireEvent.change(input, { target: { value: 'old' } });
  await waitFor(() => expect(requests.length).toBe(1));
  fireEvent.change(input, { target: { value: 'new' } });
  await waitFor(() => expect(requests.length).toBe(2));
  await act(async () => { requests[1].next(response([stateFrame('completed')])); });
  expect(await screen.findByText('completed')).toBeInTheDocument();
  await act(async () => { requests[0].next(response([stateFrame('stale')])); });
  expect(screen.getByText('completed')).toBeInTheDocument();
  expect(screen.queryByText('stale')).not.toBeInTheDocument();
});
