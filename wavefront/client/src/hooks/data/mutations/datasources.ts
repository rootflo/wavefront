import floConsoleService from '@app/api';
import { getAllDatasourcesKey, getAllDynamicQueriesKey, getDatasourceKey, readDynamicQueryKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

type DatasourceFields = { name: string; type: string; config: Record<string, unknown>; description?: string };

export const useCreateDatasource = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ name, type, config, description }: DatasourceFields) =>
      floConsoleService.datasourcesService.createDatasource(name, type, config, description),
    successMessage: 'Datasource created successfully',
    errorMessage: 'Failed to create datasource',
    invalidate: () => [appId && getAllDatasourcesKey(appId)],
  });

export const useUpdateDatasource = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ datasourceId, name, type, config, description }: DatasourceFields & { datasourceId: string }) =>
      floConsoleService.datasourcesService.updateDatasource(datasourceId, name, type, config, description),
    successMessage: 'Datasource updated successfully',
    errorMessage: 'Failed to update datasource',
    invalidate: ({ datasourceId }) =>
      appId ? [getAllDatasourcesKey(appId), getDatasourceKey(appId, datasourceId)] : [],
  });

export const useDeleteDatasource = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (datasourceId: string) => floConsoleService.datasourcesService.deleteDatasource(datasourceId),
    successMessage: 'Datasource deleted successfully',
    errorMessage: 'Failed to delete datasource',
    invalidate: () => [appId && getAllDatasourcesKey(appId)],
  });

/** The dynamic query API reports success as meta.code 1 rather than through the HTTP status. */
const SUCCESS_CODE = 1;

/** Creates a dynamic query, or replaces one with the same id (the API has a single save endpoint). */
export const useSaveDynamicQuery = (appId: string | undefined, datasourceId: string | undefined) =>
  useResourceMutation({
    mutationFn: async ({ content, isUpdate }: { content: string; isUpdate?: boolean; queryId?: string }) => {
      const response = await floConsoleService.datasourcesService.createDynamicQuery(datasourceId!, content);
      if (response.data.meta?.code !== SUCCESS_CODE) {
        throw new Error(`Error while ${isUpdate ? 'updating' : 'creating'} dynamic query`);
      }
      return response;
    },
    successMessage: (_, { isUpdate }) => `Dynamic query ${isUpdate ? 'updated' : 'created'} successfully`,
    errorMessage: 'Error while saving dynamic query',
    invalidate: ({ queryId }) =>
      appId && datasourceId
        ? [getAllDynamicQueriesKey(appId, datasourceId), queryId && readDynamicQueryKey(appId, datasourceId, queryId)]
        : [],
  });

export const useDeleteDynamicQuery = (appId: string | undefined, datasourceId: string | undefined) =>
  useResourceMutation({
    mutationFn: async (queryId: string) => {
      const response = await floConsoleService.datasourcesService.deleteDynamicQuery(datasourceId!, queryId);
      if (response?.data.meta?.code !== SUCCESS_CODE) throw new Error('Error while deleting dynamic query');
      return response;
    },
    successMessage: 'Dynamic query deleted successfully',
    errorMessage: 'Error while deleting dynamic query',
    invalidate: () => [appId && datasourceId && getAllDynamicQueriesKey(appId, datasourceId)],
  });
