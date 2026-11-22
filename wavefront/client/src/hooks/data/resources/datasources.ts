import floConsoleService from '@app/api';
import { Datasource, DynamicQuery, ReadDynamicQueryData } from '@app/types/datasource';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import {
  getAllDatasourcesKey,
  getDatasourceKey,
  getAllDynamicQueriesKey,
  readDynamicQueryKey,
  getDatasourceResourcesKey,
} from '../query-keys';

// Reads

const getAllDatasourcesQueryFn = async () => {
  const {
    data: { data = { datasources: [] } },
  } = await floConsoleService.datasourcesService.getAllDatasources();
  return data.datasources;
};

const getDatasourceQueryFn = async (datasourceId: string): Promise<Datasource | null> => {
  const response = await floConsoleService.datasourcesService.getDatasource(datasourceId);
  if (response.data?.data) {
    const responseData = response.data.data as {
      name?: string;
      type?: string;
      config?: string | Record<string, unknown>;
      description?: string;
      created_at?: string;
      updated_at?: string;
    };
    return {
      id: datasourceId,
      name: responseData.name || 'Unknown',
      type: responseData.type || 'unknown',
      config: typeof responseData.config === 'string' ? JSON.parse(responseData.config) : responseData.config || {},
      description: responseData.description || '',
      created_at: responseData.created_at,
      updated_at: responseData.updated_at,
    };
  }
  return null;
};

const getAllDynamicQueriesQueryFn = async (datasourceId: string): Promise<DynamicQuery[]> => {
  const response = await floConsoleService.datasourcesService.getAllDynamicQueries(datasourceId);
  if (response.data?.data?.yamls) {
    return response.data.data.yamls;
  }
  return [];
};

const readDynamicQueryQueryFn = async (datasourceId: string, queryId: string): Promise<ReadDynamicQueryData | null> => {
  const response = await floConsoleService.datasourcesService.readDynamicQuery(datasourceId, queryId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getDatasourceResourcesQueryFn = async (datasourceId: string): Promise<string[]> => {
  const response = await floConsoleService.datasourcesService.getDatasourceResources(datasourceId);
  if (response.data?.data?.resources) {
    return response.data.data.resources;
  }
  return [];
};

export const useGetAllDatasources = (appId: string | undefined): UseQueryResult<Datasource[], Error> => {
  return useQueryInit(getAllDatasourcesKey(appId || ''), getAllDatasourcesQueryFn, !!appId);
};

export const useGetDatasource = (
  appId: string | undefined,
  datasourceId: string | undefined
): UseQueryResult<Datasource | null, Error> => {
  return useQueryInit(
    getDatasourceKey(appId || '', datasourceId || ''),
    () => getDatasourceQueryFn(datasourceId!),
    !!appId && !!datasourceId
  );
};

export const useGetAllDynamicQueries = (
  appId: string | undefined,
  datasourceId: string | undefined
): UseQueryResult<DynamicQuery[], Error> => {
  return useQueryInit(
    getAllDynamicQueriesKey(appId || '', datasourceId || ''),
    () => getAllDynamicQueriesQueryFn(datasourceId!),
    !!appId && !!datasourceId
  );
};

export const useReadDynamicQuery = (
  appId: string | undefined,
  datasourceId: string | undefined,
  queryId: string | undefined
): UseQueryResult<ReadDynamicQueryData | null, Error> => {
  return useQueryInit(
    readDynamicQueryKey(appId || '', datasourceId || '', queryId || ''),
    () => readDynamicQueryQueryFn(datasourceId!, queryId!),
    !!appId && !!datasourceId && !!queryId
  );
};

/** A SQL datasource's tables. Shared by the Info, Data and Operations tabs, so it's fetched once for all. */
export const useGetDatasourceResources = (
  appId: string | undefined,
  datasourceId: string | undefined,
  enabled = true
): UseQueryResult<string[], Error> => {
  return useQueryInit(
    getDatasourceResourcesKey(appId || '', datasourceId || ''),
    () => getDatasourceResourcesQueryFn(datasourceId!),
    enabled && !!appId && !!datasourceId
  );
};

// Writes

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
