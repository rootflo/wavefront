import ListHeader from '@app/components/ListHeader';
import ResourceCard, { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { KeyRound, Power } from 'lucide-react';
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
import { EMAIL_PROVIDERS_CONFIG } from '@app/config/email-providers';
import { useGetOAuthApps } from '@app/hooks';
import { getOAuthAppsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage, formatAppName } from '@app/lib/utils';
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
                onClick={() => navigate(`/apps/${app}/oauth-apps`)}
                className="hover:text-foreground cursor-pointer"
              >
                OAuth Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <ListHeader
        title="OAuth Apps"
        count={filteredApps.length || undefined}
        subtitle={<>OAuth applications mailboxes connect through for {selectedApp?.app_name}</>}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search oauth apps' }}
        primary={{ label: 'Register app', onClick: handleCreateClick }}
      />

      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, index) => (
            <ResourceCardSkeleton key={index} showDescription metadataCount={3} />
          ))
        ) : filteredApps.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
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
          <>
            {filteredApps.map((oauthApp) => {
              const providerName = EMAIL_PROVIDERS_CONFIG[oauthApp.provider]?.name || oauthApp.provider;
              return (
                <ResourceCard
                  key={oauthApp.id}
                  icon={KeyRound}
                  title={formatAppName(oauthApp.name)}
                  description={oauthApp.description || undefined}
                  metadata={[
                    { label: 'Provider', value: providerName },
                    {
                      label: 'Status',
                      value: oauthApp.is_enabled ? 'Enabled' : 'Disabled',
                      className: oauthApp.is_enabled
                        ? 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300'
                        : 'bg-frost-glass-strong frost-text-subtle',
                    },
                    {
                      label: 'Client secret',
                      value: oauthApp.has_client_secret ? 'Secret stored' : 'Secret missing',
                      className: oauthApp.has_client_secret
                        ? 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300'
                        : 'bg-rose-400/15 text-rose-800 dark:text-rose-300',
                    },
                  ]}
                  onEditClick={() => void handleEditClick(oauthApp)}
                  onDeleteClick={() => setDeleteItem(oauthApp)}
                  deleteTitle="Delete OAuth app"
                  extraActions={[
                    {
                      label: oauthApp.is_enabled ? 'Disable' : 'Enable',
                      icon: Power,
                      disabled: busyId === oauthApp.id,
                      onClick: () => void handleToggleEnabled(oauthApp),
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
