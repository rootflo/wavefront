import ListHeader from '@app/components/ListHeader';
import ResourceCard, { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { KeyRound, Power } from 'lucide-react';
import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { EMAIL_PROVIDERS_CONFIG } from '@app/config/email-providers';
import { useDeleteOAuthApp, useGetOAuthApps, useSetOAuthAppEnabled } from '@app/hooks';
import { extractErrorMessage } from '@app/lib/errors';
import { formatAppName } from '@app/utils/string-formatting';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { OAuthApp } from '@app/types/oauth-app';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import OAuthAppFormDialog from './OAuthAppFormDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const OAuthAppsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const { notifyError } = useNotifyStore();
  const setOAuthAppEnabled = useSetOAuthAppEnabled(app);
  const deleteOAuthApp = useDeleteOAuthApp(app);
  const deletion = useDeleteConfirm<OAuthApp>((item) => deleteOAuthApp.mutateAsync(item.id));
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<OAuthApp | null>(null);

  const { data: oauthApps = [], isLoading } = useGetOAuthApps(app);

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

  const handleToggleEnabled = (oauthApp: OAuthApp) => {
    setOAuthAppEnabled.mutate({ oauthAppId: oauthApp.id, name: oauthApp.name, enabled: !oauthApp.is_enabled });
  };
  const filteredApps = oauthApps.filter((oauthApp) =>
    matchesSearch(searchQuery, oauthApp.name, oauthApp.provider, oauthApp.description)
  );

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb className="shrink-0" items={[{ label: 'OAuth Apps', to: `/apps/${app}/oauth-apps` }]} />

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
                  onDeleteClick={() => deletion.ask(oauthApp)}
                  deleteTitle="Delete OAuth app"
                  extraActions={[
                    {
                      label: oauthApp.is_enabled ? 'Disable' : 'Enable',
                      icon: Power,
                      disabled:
                        setOAuthAppEnabled.isPending && setOAuthAppEnabled.variables?.oauthAppId === oauthApp.id,
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
        {...deletion.dialogProps}
        title="Delete OAuth App"
        message={`Are you sure you want to delete "${deletion.item?.name}"? Mailboxes connected through it stop working until another app is attached.`}
      />

      <OAuthAppFormDialog isOpen={formOpen} onOpenChange={setFormOpen} oauthApp={editItem} />
    </div>
  );
};

export default OAuthAppsPage;
