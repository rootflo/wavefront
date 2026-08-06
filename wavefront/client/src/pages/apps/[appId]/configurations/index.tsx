import floConsoleService from '@app/api';
import ConfigurationCard from '@app/components/ConfigurationCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { useGetConfigurations } from '@app/hooks';
import { getConfigurationsKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { ConfigurationListItem } from '@app/types/configuration';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateConfigurationDialog from './CreateConfigurationDialog';

const ConfigurationsManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteItem, setDeleteItem] = useState<ConfigurationListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { notifySuccess } = useNotifyStore();

  const { data: configurations = [], isLoading: loading } = useGetConfigurations(appId);

  const filteredConfigurations = configurations.filter(
    (configuration) =>
      configuration.key.toLowerCase().includes(searchTerm.toLowerCase()) ||
      configuration.namespace.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getConfigurationsKey(appId || ''),
    });

  const handleCreateConfiguration = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    invalidate();
    setCreateDialogOpen(false);
  };

  const handleConfigurationClick = (configuration: ConfigurationListItem) => {
    navigate(
      `/apps/${appId}/configurations/${encodeURIComponent(configuration.namespace)}/${encodeURIComponent(
        configuration.key
      )}`
    );
  };

  const handleDeleteClick = (e: React.MouseEvent, configuration: ConfigurationListItem) => {
    e.stopPropagation();
    setDeleteItem(configuration);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.configurationService.deleteConfiguration(deleteItem.namespace, deleteItem.key);
      notifySuccess('Configuration deleted successfully');
      invalidate();
      setDeleteItem(null);
    } catch (error) {
      console.error('Error deleting configuration:', error);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  return (
    <div className="flex h-full w-full flex-col p-8">
      <Breadcrumb className="mb-4">
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
                onClick={() => navigate(`/apps/${appId}/configurations`)}
                className="hover:text-foreground cursor-pointer"
              >
                Configurations
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">Configurations</h1>
          <p className="animate-fade-in mt-2 text-gray-600">Static reference data workflows read at runtime</p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Button onClick={handleCreateConfiguration}>Create Configuration</Button>
        </div>
      </div>
      <div className="grid gap-6 overflow-y-auto py-2 sm:grid-cols-2 lg:grid-cols-3">
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
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Configuration"
        message={`Are you sure you want to delete "${deleteItem?.key}" from namespace "${deleteItem?.namespace}"? Any workflow reading it will start failing. This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {appId && (
        <CreateConfigurationDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default ConfigurationsManagement;
