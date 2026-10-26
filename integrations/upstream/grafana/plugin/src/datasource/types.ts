import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

export type DarkmoonQueryType =
  | 'overview'
  | 'campaigns'
  | 'findings'
  | 'targets'
  | 'timeseries'
  | 'pullrequests'
  | 'retest';

export interface DarkmoonQuery extends DataQuery {
  queryType: DarkmoonQueryType;

  // findings / targets filters
  severity?: string;
  status?: string;
  category?: string;
  campaign_id?: string;
  target_id?: string;
  project_id?: string;
  risk_level?: string;

  // timeseries
  metric?: string;
  group?: string;
  params?: Record<string, string>;

  // retest
  retest_id?: string;
}

export const DEFAULT_QUERY: Partial<DarkmoonQuery> = {
  queryType: 'overview',
};

/**
 * Non-secret datasource options (jsonData).
 */
export interface DarkmoonDataSourceOptions extends DataSourceJsonData {
  baseUrl?: string;
  mode?: 'auto' | 'oss' | 'pro';
}

/**
 * Secure fields. Only a boolean "is configured" flag is ever exposed to the
 * frontend; the token value itself lives exclusively in the backend.
 */
export interface DarkmoonSecureJsonData {
  darkmoonToken?: string;
}
