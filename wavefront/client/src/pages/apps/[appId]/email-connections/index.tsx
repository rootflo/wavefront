import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Badge } from '@app/components/ui/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
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
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-8">
      <Breadcrumb className="mb-4 shrink-0">
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

      <div className="mb-8 flex w-full shrink-0 items-start justify-between">
        <div>
          <h1 className="animate-fade-in frost-text text-3xl font-bold">Emails</h1>
          <p className="animate-fade-in frost-text-muted mt-2">
            Mailboxes {selectedApp?.app_name} can read and send on behalf of
          </p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <Button onClick={() => setConnectOpen(true)}>Connect Mailbox</Button>
        </div>
      </div>

      {isLoading ? (
        <p className="frost-text-muted text-sm">Loading emails...</p>
      ) : filteredConnections.length === 0 ? (
        <div className="mt-10 flex justify-center">
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
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Mailbox</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Capabilities</TableHead>
                <TableHead>Platform sender</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredConnections.map((connection) => {
                const statusBadge = getConnectionStatusBadge(connection.status);
                const capabilities = grantedCapabilities(connection);
                const providerName = EMAIL_PROVIDERS_CONFIG[connection.provider]?.name || connection.provider;

                return (
                  <TableRow key={connection.id}>
                    <TableCell className="max-w-[200px] truncate font-medium" title={connection.name}>
                      {formatAppName(connection.name)}
                    </TableCell>
                    <TableCell className="max-w-[240px] truncate" title={connection.mailbox_email}>
                      {connection.mailbox_email}
                      {connection.last_error ? (
                        <p className="mt-0.5 max-w-[240px] truncate text-xs text-red-500" title={connection.last_error}>
                          {connection.last_error}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell className="frost-text-muted">{providerName}</TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn(statusBadge.bg, statusBadge.text, 'border-0 font-normal')}
                      >
                        {statusBadge.label}
                      </Badge>
                    </TableCell>
                    <TableCell className="frost-text-muted">
                      {capabilities.length > 0 ? capabilities.join(', ') : '—'}
                    </TableCell>
                    <TableCell className="frost-text-muted">{connection.is_primary ? 'Primary' : '—'}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={connection.status === 'pending_auth'}
                          loading={busyKey === `${connection.id}:verify`}
                          onClick={() => void handleVerify(connection)}
                        >
                          Verify
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          loading={busyKey === `${connection.id}:authorize`}
                          onClick={() => void handleReauthorize(connection)}
                        >
                          {connection.status === 'active' ? 'Re-consent' : 'Authorize'}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={connection.is_primary || connection.status !== 'active'}
                          loading={busyKey === `${connection.id}:primary`}
                          onClick={() => void handleSetPrimary(connection)}
                        >
                          Set as Primary
                        </Button>
                        <Button variant="destructive" size="sm" onClick={() => setDeleteItem(connection)}>
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

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
