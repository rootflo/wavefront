import ListHeader from '@app/components/ListHeader';
import ResourceCard, { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { Mail, ShieldCheck, KeyRound, Star } from 'lucide-react';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { EMAIL_CAPABILITIES, EMAIL_PROVIDERS_CONFIG, getConnectionStatusBadge } from '@app/config/email-providers';
import {
  useAuthorizeEmailConnection,
  useDeleteEmailConnection,
  useGetEmailConnections,
  useSetPrimaryEmailConnection,
  useVerifyEmailConnection,
} from '@app/hooks';
import { cn } from '@app/lib/utils';
import { formatAppName } from '@app/utils/string-formatting';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { EmailCapability, EmailConnection } from '@app/types/email';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import ConnectMailboxDialog from './ConnectMailboxDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

/** Which capabilities a connection's granted scopes actually cover. Scopes are
 *  provider strings, so match on the capability name they contain. */
const grantedCapabilities = (connection: EmailConnection): EmailCapability[] => {
  const scopes = (connection.granted_scopes || '').toLowerCase();
  return EMAIL_CAPABILITIES.filter((capability) => {
    if (capability.value === 'send') return scopes.includes('send');
    if (capability.value === 'modify') return scopes.includes('modify') || scopes.includes('readwrite');
    return scopes.includes('read');
  }).map((capability) => capability.value);
};

const EmailConnectionsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const { notifyError } = useNotifyStore();
  const authorizeConnection = useAuthorizeEmailConnection();
  const setPrimary = useSetPrimaryEmailConnection(app);
  const verifyConnection = useVerifyEmailConnection(app);
  const deleteConnection = useDeleteEmailConnection(app);
  const deletion = useDeleteConfirm<EmailConnection>((item) => deleteConnection.mutateAsync(item.id));
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [connectOpen, setConnectOpen] = useState(false);

  const { data: connections = [], isLoading } = useGetEmailConnections(app);

  const handleReauthorize = (connection: EmailConnection) => {
    const capabilities =
      grantedCapabilities(connection).length > 0 ? grantedCapabilities(connection) : (['read'] as EmailCapability[]);
    const emailsPageUrl = `${window.location.origin}/apps/${app}/email-connections`;
    authorizeConnection.mutate(
      {
        connectionId: connection.id,
        data: { capabilities, success_redirect_url: emailsPageUrl, failure_redirect_url: emailsPageUrl },
      },
      {
        onSuccess: (response) => {
          const authorizationUrl = response.data?.data?.authorization_url;
          if (!authorizationUrl) {
            notifyError('No consent URL was returned');
            return;
          }
          window.location.assign(authorizationUrl);
        },
      }
    );
  };

  const handleSetPrimary = (connection: EmailConnection) => {
    setPrimary.mutate({ connectionId: connection.id, mailboxEmail: connection.mailbox_email });
  };

  const handleVerify = (connection: EmailConnection) => {
    verifyConnection.mutate({ connectionId: connection.id, mailboxEmail: connection.mailbox_email });
  };

  /** Whether `mutation` is running for this connection, to disable just that row's button. */
  const isBusy = (mutation: { isPending: boolean; variables?: unknown }, connectionId: string) => {
    if (!mutation.isPending) return false;
    const vars = mutation.variables as { connectionId?: string } | undefined;
    return vars?.connectionId === connectionId;
  };

  const filteredConnections = connections.filter((connection) =>
    matchesSearch(searchQuery, connection.name, connection.mailbox_email, connection.provider)
  );

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb className="shrink-0" items={[{ label: 'Emails', to: `/apps/${app}/email-connections` }]} />

      <ListHeader
        title="Emails"
        count={filteredConnections.length || undefined}
        subtitle={<>Mailboxes {selectedApp?.app_name} can read and send on behalf of</>}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search emails' }}
        primary={{ label: 'Connect mailbox', onClick: () => setConnectOpen(true) }}
      />

      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, index) => (
            <ResourceCardSkeleton key={index} showDescription metadataCount={3} />
          ))
        ) : filteredConnections.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No emails found"
              description={
                searchQuery
                  ? 'No emails found matching your search.'
                  : 'Connect a mailbox so agents, triggers and scheduled jobs can use it'
              }
              actionText="Connect Mailbox"
              onActionClick={() => setConnectOpen(true)}
            />
          </div>
        ) : (
          <>
            {filteredConnections.map((connection) => {
              const statusBadge = getConnectionStatusBadge(connection.status);
              const capabilities = grantedCapabilities(connection);
              const providerName = EMAIL_PROVIDERS_CONFIG[connection.provider]?.name || connection.provider;
              return (
                <ResourceCard
                  key={connection.id}
                  icon={Mail}
                  title={formatAppName(connection.name)}
                  description={connection.last_error || connection.mailbox_email}
                  metadata={[
                    { label: 'Provider', value: providerName },
                    { label: 'Status', value: statusBadge.label, className: cn(statusBadge.bg, statusBadge.text) },
                    ...(capabilities.length > 0 ? [{ label: 'Capabilities', value: capabilities.join(', ') }] : []),
                    ...(connection.is_primary ? [{ label: 'Platform sender', value: 'Primary' }] : []),
                  ]}
                  onDeleteClick={() => deletion.ask(connection)}
                  deleteTitle="Delete connection"
                  extraActions={[
                    {
                      label: 'Verify',
                      icon: ShieldCheck,
                      disabled: connection.status === 'pending_auth' || isBusy(verifyConnection, connection.id),
                      onClick: () => void handleVerify(connection),
                    },
                    {
                      label: connection.status === 'active' ? 'Re-consent' : 'Authorize',
                      icon: KeyRound,
                      disabled: isBusy(authorizeConnection, connection.id),
                      onClick: () => void handleReauthorize(connection),
                    },
                    {
                      label: 'Set as Primary',
                      icon: Star,
                      disabled:
                        connection.is_primary || connection.status !== 'active' || isBusy(setPrimary, connection.id),
                      onClick: () => void handleSetPrimary(connection),
                    },
                  ]}
                />
              );
            })}
          </>
        )}
      </div>

      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Email Connection"
        message={`Are you sure you want to delete "${deletion.item?.mailbox_email}"? Triggers, jobs and agents using it stop working.`}
      />

      {app && <ConnectMailboxDialog isOpen={connectOpen} onOpenChange={setConnectOpen} appId={app} />}
    </div>
  );
};

export default EmailConnectionsPage;
