import ListHeader from '@app/components/ListHeader';
import ConfigurationCard from '@app/components/ConfigurationCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { useDeleteConfiguration, useGetConfigurations } from '@app/hooks';
import { ConfigurationListItem } from '@app/types/configuration';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateConfigurationDialog from './CreateConfigurationDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const ConfigurationsManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const deleteConfiguration = useDeleteConfiguration(appId);
  const deletion = useDeleteConfirm<ConfigurationListItem>((item) =>
    deleteConfiguration.mutateAsync({ namespace: item.namespace, key: item.key })
  );
  const [searchTerm, setSearchTerm] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { data: configurations = [], isLoading: loading } = useGetConfigurations(appId);

  const filteredConfigurations = configurations.filter((configuration) =>
    matchesSearch(searchTerm, configuration.key, configuration.namespace)
  );

  const handleCreateConfiguration = () => {
    setCreateDialogOpen(true);
  };

  const handleConfigurationClick = (configuration: ConfigurationListItem) => {
    navigate(
      `/apps/${appId}/configurations/${encodeURIComponent(configuration.namespace)}/${encodeURIComponent(
        configuration.key
      )}`
    );
  };

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Configurations', to: `/apps/${appId}/configurations` }]} />

      <ListHeader
        title="Configurations"
        count={filteredConfigurations.length || undefined}
        subtitle={<>Static reference data workflows read at runtime</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search configurations' }}
        primary={{ label: 'Create configuration', onClick: handleCreateConfiguration }}
      />
      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={1} />
            ))}
          </>
        ) : filteredConfigurations.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No configurations found"
              description="Get started by creating your first configuration"
              actionText="Create Configuration"
              onActionClick={handleCreateConfiguration}
            />
          </div>
        ) : (
          <>
            {filteredConfigurations.map((configuration) => (
              <ConfigurationCard
                key={configuration.id}
                configuration={configuration}
                onClick={handleConfigurationClick}
                onDeleteClick={(e, item) => deletion.ask(item, e)}
              />
            ))}
          </>
        )}
      </div>

      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Configuration"
        message={`Are you sure you want to delete "${deletion.item?.key}" from namespace "${deletion.item?.namespace}"? Any workflow reading it will start failing. This action cannot be undone.`}
      />

      {appId && (
        <CreateConfigurationDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={appId} />
      )}
    </div>
  );
};

export default ConfigurationsManagement;
