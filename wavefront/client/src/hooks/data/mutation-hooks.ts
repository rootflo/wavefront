import {
  QueryClient,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { getAgentKey, getAgentsKey, getAppByIdKey } from "./query-keys";
import {
  deleteAgentMutationFn,
  updateAgentMutationFn,
  updateAppFn,
} from "./mutation-functions";
import { useNotifyStore } from "@app/store";

/**
 * Hook for deleting an agent
 */
export const useDeleteAgent = (appId: string | undefined) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: deleteAgentMutationFn,
    onSuccess: () => {
      notifySuccess("Agent deleted successfully");
      // Invalidate all agents queries for this appId to refetch
      if (appId) {
        queryClient.invalidateQueries({ queryKey: getAgentsKey(appId) });
      }
    },
    onError: (error) => {
      console.error("Error deleting agent:", error);
      notifyError("Failed to delete agent");
    },
  });
};

/**
 * Hook for updating an agent
 */
export const useUpdateAgent = (
  appId: string | undefined,
  agentId: string | undefined
) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  return useMutation({
    mutationFn: updateAgentMutationFn,
    onSuccess: () => {
      notifySuccess("Agent updated successfully");
      // Invalidate agent queries to refetch updated data
      if (appId && agentId) {
        queryClient.invalidateQueries({
          queryKey: getAgentKey(appId, agentId),
        });
        queryClient.invalidateQueries({ queryKey: getAgentsKey(appId) });
      }
    },
    onError: (error) => {
      console.error("Error updating agent:", error);
      notifyError("Failed to update agent");
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
      notifySuccess("App updated successfully");
    },
    onError: () => {
      notifyError("Failed to update app");
    },
  });
};
