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
import { EMAIL_PROVIDERS_CONFIG } from '@app/config/email-providers';
import { useGetOAuthApps } from '@app/hooks';
import { getOAuthAppsKey } from '@app/hooks/data/query-keys';
import { cn, extractErrorMessage, formatAppName } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { OAuthApp } from '@app/types/oauth-app';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import OAuthAppFormDialog from './OAuthAppFormDialog';

const OAuthAppsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<OAuthApp | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<OAuthApp | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const { data: oauthApps = [], isLoading } = useGetOAuthApps(app);

  const refresh = () => queryClient.invalidateQueries({ queryKey: getOAuthAppsKey(app || '') });

  const handleCreateClick = () => {
    setEditItem(null);
    setFormOpen(true);
  };

  const handleEditClick = async (oauthApp: OAuthApp) => {
    try {
      const response = await floConsoleService.oauthAppService.getOAuthApp(oauthApp.id);
      setEditItem(response.data?.data?.app ?? oauthApp);
      setFormOpen(true);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to load OAuth app');
    }
  };

  const handleToggleEnabled = async (oauthApp: OAuthApp) => {
    setBusyId(oauthApp.id);
    try {
      if (oauthApp.is_enabled) {
        await floConsoleService.oauthAppService.disableOAuthApp(oauthApp.id);
        notifySuccess(`${oauthApp.name} disabled`);
      } else {
        await floConsoleService.oauthAppService.enableOAuthApp(oauthApp.id);
        notifySuccess(`${oauthApp.name} enabled`);
      }
      refresh();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to update OAuth app');
    } finally {
      setBusyId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.oauthAppService.deleteOAuthApp(deleteItem.id);
      notifySuccess('OAuth app deleted successfully');
      refresh();
      setDeleteItem(null);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to delete OAuth app');
    } finally {
      setDeleting(false);
    }
  };

  const filteredApps = oauthApps.filter((oauthApp) => {
    const query = searchQuery.toLowerCase();
    return (
      oauthApp.name.toLowerCase().includes(query) ||
      oauthApp.provider.toLowerCase().includes(query) ||
      (oauthApp.description || '').toLowerCase().includes(query)
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
                onClick={() => navigate(`/apps/${app}/oauth-apps`)}
                className="hover:text-foreground cursor-pointer"
              >
                OAuth Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full shrink-0 items-start justify-between">
        <div>
          <h1 className="animate-fade-in frost-text text-3xl font-bold">OAuth Apps</h1>
          <p className="animate-fade-in frost-text-muted mt-2">
            OAuth applications mailboxes connect through for {selectedApp?.app_name}
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
          <Button onClick={handleCreateClick}>Register App</Button>
        </div>
      </div>

      {isLoading ? (
        <p className="frost-text-muted text-sm">Loading OAuth apps...</p>
      ) : filteredApps.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No OAuth apps found"
            description={
              searchQuery
                ? 'No OAuth apps found matching your search.'
                : 'Register an OAuth app before connecting a mailbox'
            }
            actionText="Register App"
            onActionClick={handleCreateClick}
          />
        </div>
      ) : (
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Client secret</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredApps.map((oauthApp) => {
                const providerName = EMAIL_PROVIDERS_CONFIG[oauthApp.provider]?.name || oauthApp.provider;

                return (
                  <TableRow key={oauthApp.id}>
                    <TableCell className="max-w-[200px] truncate font-medium" title={oauthApp.name}>
                      {formatAppName(oauthApp.name)}
                    </TableCell>
                    <TableCell className="frost-text-muted max-w-[280px] truncate" title={oauthApp.description || ''}>
                      {oauthApp.description || '—'}
                    </TableCell>
                    <TableCell className="frost-text-muted">{providerName}</TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn(
                          'border-0 font-normal',
                          oauthApp.is_enabled
                            ? 'bg-emerald-400/15 text-emerald-800'
                            : 'bg-frost-glass-strong frost-text-subtle'
                        )}
                      >
                        {oauthApp.is_enabled ? 'Enabled' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn(
                          'border-0 font-normal',
                          oauthApp.has_client_secret
                            ? 'bg-emerald-400/15 text-emerald-800'
                            : 'bg-rose-400/15 text-rose-800'
                        )}
                      >
                        {oauthApp.has_client_secret ? 'Stored' : 'Missing'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          loading={busyId === oauthApp.id}
                          onClick={() => void handleToggleEnabled(oauthApp)}
                        >
                          {oauthApp.is_enabled ? 'Disable' : 'Enable'}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => void handleEditClick(oauthApp)}>
                          Edit
                        </Button>
                        <Button variant="destructive" size="sm" onClick={() => setDeleteItem(oauthApp)}>
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
        title="Delete OAuth App"
        message={`Are you sure you want to delete "${deleteItem?.name}"? Mailboxes connected through it stop working until another app is attached.`}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteItem(null)}
        loading={deleting}
      />

      <OAuthAppFormDialog isOpen={formOpen} onOpenChange={setFormOpen} oauthApp={editItem} onSuccess={refresh} />
    </div>
  );
};

export default OAuthAppsPage;
