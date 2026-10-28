import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { AppRootProps } from '@grafana/data';
import { render, screen } from '@testing-library/react';
import App from './App';

jest.mock('../DatasourceView', () => ({
  __esModule: true,
  VIEWS: [{ type: 'overview', label: 'Overview' }, { type: 'retest', label: 'Retests' }],
  default: ({ type, defaultUid }: { type: string; defaultUid?: string }) =>
    <p>{`Darkmoon ${type} datasource ${defaultUid || 'unselected'}`}</p>,
}));

const props = { meta: { jsonData: { datasourceUid: 'darkmoon-1' } } } as unknown as AppRootProps;

test('routes to live datasource-backed overview using configured UID', () => {
  render(<MemoryRouter initialEntries={['/overview']}><App {...props} /></MemoryRouter>);
  expect(screen.getByText('Darkmoon overview datasource darkmoon-1')).toBeInTheDocument();
});

test('exposes lifecycle-only retest page without inventing assessment state', () => {
  render(<MemoryRouter initialEntries={['/retest']}><App {...props} /></MemoryRouter>);
  expect(screen.getByText('Darkmoon retest datasource darkmoon-1')).toBeInTheDocument();
});
