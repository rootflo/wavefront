import ListHeader from '@app/components/ListHeader';
import ResourceCard, { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { Mail, ShieldCheck, KeyRound, Star } from 'lucide-react';
import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { EMAIL_CAPABILITIES, EMAIL_PROVIDERS_CONFIG, getConnectionStatusBadge } from '@app/config/email-providers';
import { useGetEmailConnections } from '@app/hooks';
import { getEmailConnectionsKey } from '@app/hooks/data/query-keys';
import { cn, extractErrorMessage, formatAppName } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { EmailCapability, EmailConnection } from '@app/types/email';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import ConnectMailboxDialog from './ConnectMailboxDialog';

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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<EmailConnection | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const { data: connections = [], isLoading } = useGetEmailConnections(app);

  const refresh = () => queryClient.invalidateQueries({ queryKey: getEmailConnectionsKey(app || '') });

  const handleReauthorize = async (connection: EmailConnection) => {
    setBusyKey(`${connection.id}:authorize`);
    try {
      const capabilities =
        grantedCapabilities(connection).length > 0 ? grantedCapabilities(connection) : (['read'] as EmailCapability[]);
      const emailsPageUrl = `${window.location.origin}/apps/${app}/email-connections`;
      const response = await floConsoleService.emailConnectionService.authorizeEmailConnection(connection.id, {
        capabilities,
        success_redirect_url: emailsPageUrl,
        failure_redirect_url: emailsPageUrl,
      });
      const authorizationUrl = response.data?.data?.authorization_url;
      if (!authorizationUrl) {
        notifyError('No consent URL was returned');
        return;
      }
      window.location.assign(authorizationUrl);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to build the consent URL');
    } finally {
      setBusyKey(null);
    }
  };

  const handleSetPrimary = async (connection: EmailConnection) => {
    setBusyKey(`${connection.id}:primary`);
    try {
      await floConsoleService.emailConnectionService.setPrimaryEmailConnection(connection.id);
      notifySuccess(`${connection.mailbox_email} is now the platform sender`);
      refresh();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to set the primary connection');
    } finally {
      setBusyKey(null);
    }
  };

  const handleVerify = async (connection: EmailConnection) => {
    setBusyKey(`${connection.id}:verify`);
    try {
      await floConsoleService.emailConnectionService.verifyEmailConnection(connection.id);
      notifySuccess(`${connection.mailbox_email} is connected`);
      refresh();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to verify the email connection');
      refresh();
    } finally {
      setBusyKey(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.emailConnectionService.deleteEmailConnection(deleteItem.id);
      notifySuccess('Email connection deleted successfully');
      refresh();
      setDeleteItem(null);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to delete the email connection');
    } finally {
      setDeleting(false);
    }
  };

  const filteredConnections = connections.filter((connection) => {
    const query = searchQuery.toLowerCase();
    return (
      connection.name.toLowerCase().includes(query) ||
      connection.mailbox_email.toLowerCase().includes(query) ||
      connection.provider.toLowerCase().includes(query)
    );
  });

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <Breadcrumb className="mb-4 hidden shrink-0 md:block">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${app}/email-connections`)}
                className="hover:text-foreground cursor-pointer"
              >
                Emails
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

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
                  onDeleteClick={() => setDeleteItem(connection)}
                  deleteTitle="Delete connection"
                  extraActions={[
                    {
                      label: 'Verify',
                      icon: ShieldCheck,
                      disabled: connection.status === 'pending_auth' || busyKey === `${connection.id}:verify`,
                      onClick: () => void handleVerify(connection),
                    },
                    {
                      label: connection.status === 'active' ? 'Re-consent' : 'Authorize',
                      icon: KeyRound,
                      disabled: busyKey === `${connection.id}:authorize`,
                      onClick: () => void handleReauthorize(connection),
                    },
                    {
                      label: 'Set as Primary',
                      icon: Star,
                      disabled:
                        connection.is_primary ||
                        connection.status !== 'active' ||
                        busyKey === `${connection.id}:primary`,
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
        isOpen={!!deleteItem}
        title="Delete Email Connection"
        message={`Are you sure you want to delete "${deleteItem?.mailbox_email}"? Triggers, jobs and agents using it stop working.`}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteItem(null)}
        loading={deleting}
      />

      {app && (
        <ConnectMailboxDialog isOpen={connectOpen} onOpenChange={setConnectOpen} appId={app} onSuccess={refresh} />
      )}
    </div>
  );
};

export default EmailConnectionsPage;
