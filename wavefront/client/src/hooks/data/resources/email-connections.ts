import floConsoleService from '@app/api';
import { EmailConnection, AuthorizeEmailConnectionRequest, CreateEmailConnectionRequest } from '@app/types/email';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getEmailConnectionsKey, getEmailConnectionKey } from '../query-keys';

// Reads

const getEmailConnectionsQueryFn = async (): Promise<EmailConnection[]> => {
  const response = await floConsoleService.emailConnectionService.getAllEmailConnections();
  if (response.data?.meta?.status === 'success' && response.data.data?.connections) {
    return response.data.data.connections;
  }
  return [];
};

const getEmailConnectionQueryFn = async (connectionId: string): Promise<EmailConnection | null> => {
  const response = await floConsoleService.emailConnectionService.getEmailConnection(connectionId);
  return response.data?.data?.connection ?? null;
};

export const useGetEmailConnections = (appId: string | undefined): UseQueryResult<EmailConnection[], Error> => {
  return useQueryInit(getEmailConnectionsKey(appId || ''), getEmailConnectionsQueryFn, !!appId);
};

export const useGetEmailConnection = (
  appId: string | undefined,
  connectionId: string | undefined
): UseQueryResult<EmailConnection | null, Error> => {
  return useQueryInit(
    getEmailConnectionKey(appId || '', connectionId || ''),
    () => getEmailConnectionQueryFn(connectionId!),
    !!appId && !!connectionId
  );
};

// Writes

type ConnectionRef = { connectionId: string; mailboxEmail: string };

/** No success toast: the caller sends the browser on to the provider's consent page. */
export const useCreateEmailConnection = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateEmailConnectionRequest) =>
      floConsoleService.emailConnectionService.createEmailConnection(data),
    errorMessage: 'Failed to start connecting the mailbox',
    invalidate: () => [appId && getEmailConnectionsKey(appId)],
  });

/** Builds a fresh consent URL for an existing connection; the caller redirects to it. */
export const useAuthorizeEmailConnection = () =>
  useResourceMutation({
    mutationFn: ({ connectionId, data }: { connectionId: string; data: AuthorizeEmailConnectionRequest }) =>
      floConsoleService.emailConnectionService.authorizeEmailConnection(connectionId, data),
    errorMessage: 'Failed to build the consent URL',
  });

export const useSetPrimaryEmailConnection = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ connectionId }: ConnectionRef) =>
      floConsoleService.emailConnectionService.setPrimaryEmailConnection(connectionId),
    successMessage: (_, { mailboxEmail }) => `${mailboxEmail} is now the platform sender`,
    errorMessage: 'Failed to set the primary connection',
    invalidate: () => [appId && getEmailConnectionsKey(appId)],
  });

/** Refetches on failure too: a failed check can still update the connection's status. */
export const useVerifyEmailConnection = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ connectionId }: ConnectionRef) =>
      floConsoleService.emailConnectionService.verifyEmailConnection(connectionId),
    successMessage: (_, { mailboxEmail }) => `${mailboxEmail} is connected`,
    errorMessage: 'Failed to verify the email connection',
    invalidate: ({ connectionId }) =>
      appId ? [getEmailConnectionsKey(appId), getEmailConnectionKey(appId, connectionId)] : [],
    invalidateOnError: true,
  });

export const useDeleteEmailConnection = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (connectionId: string) => floConsoleService.emailConnectionService.deleteEmailConnection(connectionId),
    successMessage: 'Email connection deleted successfully',
    errorMessage: 'Failed to delete the email connection',
    invalidate: () => [appId && getEmailConnectionsKey(appId)],
  });
