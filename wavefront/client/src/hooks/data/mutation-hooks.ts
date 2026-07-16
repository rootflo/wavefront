import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getAgentKey,
  getAgentsKey,
  getAgentVersionsKey,
  getWorkflowVersionsKey,
  getWorkflowsKey,
  getAppByIdKey,
  getConsoleUsersKey,
  getUserKey,
} from './query-keys';
import {
  createUserMutationFn,
  deleteAgentMutationFn,
  deleteUserMutationFn,
  updateAgentMutationFn,
  updateAppFn,
  updateUserMutationFn,
  promoteAgentVersionMutationFn,
  deleteAgentVersionMutationFn,
  promoteWorkflowVersionMutationFn,
  deleteWorkflowVersionMutationFn,
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

/**
 * Agent version management hooks
 */
export const usePromoteAgentVersion = (appId: string | undefined, agentId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: promoteAgentVersionMutationFn,
    onSuccess: () => {
      notifySuccess('Version promoted successfully');
      if (appId && agentId) {
        queryClient.invalidateQueries({ queryKey: getAgentVersionsKey(appId, agentId) });
        queryClient.invalidateQueries({ queryKey: getAgentKey(appId, agentId) });
        queryClient.invalidateQueries({ queryKey: getAgentsKey(appId) });
      }
    },
    onError: (error) => {
      console.error('Error promoting agent version:', error);
      notifyError(extractErrorMessage(error) || 'Failed to promote version');
    },
  });
};

export const useDeleteAgentVersion = (appId: string | undefined, agentId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: deleteAgentVersionMutationFn,
    onSuccess: () => {
      notifySuccess('Version deleted successfully');
      if (appId && agentId) {
        queryClient.invalidateQueries({ queryKey: getAgentVersionsKey(appId, agentId) });
        queryClient.invalidateQueries({ queryKey: getAgentKey(appId, agentId) });
      }
    },
    onError: (error) => {
      console.error('Error deleting agent version:', error);
      notifyError(extractErrorMessage(error) || 'Failed to delete version');
    },
  });
};

/**
 * Workflow version management hooks
 */
export const usePromoteWorkflowVersion = (appId: string | undefined, workflowId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: promoteWorkflowVersionMutationFn,
    onSuccess: () => {
      notifySuccess('Version promoted successfully');
      if (appId && workflowId) {
        queryClient.invalidateQueries({ queryKey: getWorkflowVersionsKey(appId, workflowId) });
        queryClient.invalidateQueries({ queryKey: getWorkflowsKey(appId) });
      }
    },
    onError: (error) => {
      console.error('Error promoting workflow version:', error);
      notifyError(extractErrorMessage(error) || 'Failed to promote version');
    },
  });
};

export const useDeleteWorkflowVersion = (appId: string | undefined, workflowId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: deleteWorkflowVersionMutationFn,
    onSuccess: () => {
      notifySuccess('Version deleted successfully');
      if (appId && workflowId) {
        queryClient.invalidateQueries({ queryKey: getWorkflowVersionsKey(appId, workflowId) });
      }
    },
    onError: (error) => {
      console.error('Error deleting workflow version:', error);
      notifyError(extractErrorMessage(error) || 'Failed to delete version');
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
      queryClient.invalidateQueries({ queryKey: getConsoleUsersKey() });
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
      queryClient.invalidateQueries({ queryKey: getConsoleUsersKey() });
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
      queryClient.invalidateQueries({ queryKey: getConsoleUsersKey() });
    },
    onError: (error) => {
      console.error('Error deleting user:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete user');
    },
  });
};
