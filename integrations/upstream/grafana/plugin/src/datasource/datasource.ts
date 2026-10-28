import { DataSourceInstanceSettings, CoreApp } from '@grafana/data';
import { DataSourceWithBackend } from '@grafana/runtime';

import { DarkmoonQuery, DarkmoonDataSourceOptions, DEFAULT_QUERY } from './types';

export class DataSource extends DataSourceWithBackend<DarkmoonQuery, DarkmoonDataSourceOptions> {
  constructor(instanceSettings: DataSourceInstanceSettings<DarkmoonDataSourceOptions>) {
    super(instanceSettings);
  }

  getDefaultQuery(_: CoreApp): Partial<DarkmoonQuery> {
    return DEFAULT_QUERY;
  }

  filterQuery(query: DarkmoonQuery): boolean {
    // A retest read needs an explicit saved identity; overview is the default.
    return query.hide !== true && (query.queryType !== 'retest' || !!query.retest_id?.trim());
  }
}
