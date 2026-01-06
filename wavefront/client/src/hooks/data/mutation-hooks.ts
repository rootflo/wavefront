import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAgentKey, getAgentsKey, getAppByIdKey, getUserKey, getUsersKey } from './query-keys';
import {
  createUserMutationFn,
  deleteAgentMutationFn,
  deleteUserMutationFn,
  updateAgentMutationFn,
  updateAppFn,
  updateUserMutationFn,
} from './mutation-functions';
import { useNotifyStore } from '@app/store';
import { extractErrorMessage } from '@app/lib/utils';

/**
 * Hook for deleting an agent
 */
export const useDeleteAgent = (appId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: deleteAgentMutationFn,
    onSuccess: () => {
      notifySuccess('Agent deleted successfully');
      // Invalidate all agents queries for this appId to refetch
      if (appId) {
        queryClient.invalidateQueries({ queryKey: getAgentsKey(appId) });
      }
    },
    onError: (error) => {
      console.error('Error deleting agent:', error);
      notifyError('Failed to delete agent');
    },
  });
};

/**
 * Hook for updating an agent
 */
export const useUpdateAgent = (appId: string | undefined, agentId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: updateAgentMutationFn,
    onSuccess: () => {
      notifySuccess('Agent updated successfully');
      // Invalidate agent queries to refetch updated data
      if (appId && agentId) {
        queryClient.invalidateQueries({
          queryKey: getAgentKey(appId, agentId),
        });
        queryClient.invalidateQueries({ queryKey: getAgentsKey(appId) });
      }
    },
    onError: (error) => {
      console.error('Error updating agent:', error);
      notifyError('Failed to update agent');
    },
  });
};

export const useUpdateApp = (
  queryClient: QueryClient,
  notifySuccess: (message: string) => void,
  notifyError: (message: string) => void
) => {
  return useMutation({
    mutationFn: updateAppFn,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: getAppByIdKey(variables.appId),
      });
      notifySuccess('App updated successfully');
    },
    onError: () => {
      notifyError('Failed to update app');
    },
  });
};

/**
 * User mutation hooks
 */
export const useCreateUser = () => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: createUserMutationFn,
    onSuccess: () => {
      notifySuccess('User created successfully');
      queryClient.invalidateQueries({ queryKey: getUsersKey() });
    },
    onError: (error) => {
      console.error('Error creating user:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create user');
    },
  });
};

export const useUpdateUser = (userId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: updateUserMutationFn,
    onSuccess: () => {
      notifySuccess('User updated successfully');
      queryClient.invalidateQueries({ queryKey: getUsersKey() });
      if (userId) {
        queryClient.invalidateQueries({ queryKey: getUserKey(userId) });
      }
    },
    onError: (error) => {
      console.error('Error updating user:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update user');
    },
  });
};

export const useDeleteUser = () => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: deleteUserMutationFn,
    onSuccess: () => {
      notifySuccess('User deleted successfully');
      queryClient.invalidateQueries({ queryKey: getUsersKey() });
    },
    onError: (error) => {
      console.error('Error deleting user:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete user');
    },
  });
};
