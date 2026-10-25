import floConsoleService from '@app/api';
import { NamespaceItem } from '@app/types/namespace';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { getNamespacesKey } from '../query-keys';

// Reads

const getNamespacesQueryFn = async (): Promise<NamespaceItem[]> => {
  const response = await floConsoleService.namespaceService.listNamespaces();
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.namespaces;
  }
  return [];
};

export const useGetNamespaces = (appId: string | undefined): UseQueryResult<NamespaceItem[], Error> => {
  return useQueryInit(getNamespacesKey(appId || ''), getNamespacesQueryFn, !!appId);
};
