import { DataSourcePlugin } from '@grafana/data';
import { DataSource } from './datasource';
import { ConfigEditor } from './components/ConfigEditor';
import { QueryEditor } from './components/QueryEditor';
import { DarkmoonQuery, DarkmoonDataSourceOptions } from './types';

export const plugin = new DataSourcePlugin<DataSource, DarkmoonQuery, DarkmoonDataSourceOptions>(DataSource)
  .setConfigEditor(ConfigEditor)
  .setQueryEditor(QueryEditor);
