import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { QueryKey, useMutation, useQueryClient } from '@tanstack/react-query';

type ResourceMutationOptions<TVars, TData> = {
  mutationFn: (vars: TVars) => Promise<TData>;
  /** Toast on success; omit when the caller reports success itself. */
  successMessage?: string | ((data: TData, vars: TVars) => string);
  /** Toast fallback when the server sends no message; false when the caller shows the error inline. */
  errorMessage: string | false;
  /** Query keys to refetch after success. Falsy entries (e.g. no appId yet) are skipped. */
  invalidate?: (vars: TVars, data?: TData) => (QueryKey | false | '' | null | undefined)[];
  /** Also refetch after a failure, when the server may have changed state anyway. */
  invalidateOnError?: boolean;
};

/** A write against the API: toasts the outcome and refreshes the affected queries. */
export const useResourceMutation = <TVars = void, TData = unknown>({
  mutationFn,
  successMessage,
  errorMessage,
  invalidate,
  invalidateOnError = false,
}: ResourceMutationOptions<TVars, TData>) => {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const refetch = (vars: TVars, data?: TData) =>
    invalidate?.(vars, data).forEach((queryKey) => {
      if (queryKey) queryClient.invalidateQueries({ queryKey });
    });

  return useMutation<TData, unknown, TVars>({
    mutationFn,
    onSuccess: (data, vars) => {
      if (successMessage) {
        notifySuccess(typeof successMessage === 'function' ? successMessage(data, vars) : successMessage);
      }
      refetch(vars, data);
    },
    onError: (error, vars) => {
      if (errorMessage !== false) {
        notifyError(extractErrorMessage(error) || errorMessage);
      }
      if (invalidateOnError) refetch(vars);
    },
  });
};
