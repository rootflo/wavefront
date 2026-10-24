import { LLM_PROVIDERS_CONFIG } from '@app/config/llm-providers';
import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import ModelCard from '@app/components/ModelCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { useGetLLMConfigs } from '@app/hooks';
import { getLLMConfigsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateModelDialog from './CreateModelDialog';

const ModelHub: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [providerFilter, setProviderFilter] = useState('all');
  const [deleteItem, setDeleteItem] = useState<LLMInferenceConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch the models
  const { data: configs = [], isLoading: loading } = useGetLLMConfigs(appId);

  const filteredConfigs = configs.filter(
    (config) =>
      (providerFilter === 'all' || config.type === providerFilter) &&
      (config.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        config.llm_model.toLowerCase().includes(searchTerm.toLowerCase()) ||
        config.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        config.type.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const providerOptions = Array.from(new Set(configs.map((config) => config.type)))
    .sort()
    .map((type) => ({ value: type, label: LLM_PROVIDERS_CONFIG[type]?.name ?? type }));

  const handleCreateConfig = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getLLMConfigsKey(appId || '') });
    setCreateDialogOpen(false);
  };

  const handleConfigClick = (modelId: string) => {
    navigate(`/apps/${appId}/model-hub/${modelId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, config: LLMInferenceConfig) => {
    e.stopPropagation();
    setDeleteItem(config);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.llmInferenceService.deleteLLMConfig(deleteItem.id);
      notifySuccess('Model deleted successfully');
      queryClient.invalidateQueries({
        queryKey: getLLMConfigsKey(appId || ''),
      });
      setDeleteItem(null);
    } catch (error) {
      console.error('Error deleting model:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete model');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <Breadcrumb className="mb-4 hidden md:block">
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
                onClick={() => navigate(`/apps/${appId}/model-hub`)}
                className="hover:text-foreground cursor-pointer"
              >
                Model Hub
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <ListHeader
        title="Model Hub"
        count={filteredConfigs.length || undefined}
        subtitle={<>Manage models for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search models' }}
        filters={
          providerOptions.length > 1 ? (
            <FilterSelect
              label="Provider"
              value={providerFilter}
              onValueChange={setProviderFilter}
              allValue="all"
              options={[{ value: 'all', label: 'All' }, ...providerOptions]}
            />
          ) : undefined
        }
        primary={{ label: 'Add model', onClick: handleCreateConfig }}
      />
      <div className="grid w-full gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={4} />
            ))}
          </>
        ) : filteredConfigs.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No models found"
              description="Get started by adding your first model to the Model Hub"
              actionText="Add model"
              onActionClick={handleCreateConfig}
            />
          </div>
        ) : (
          <>
            {filteredConfigs.map((config) => (
              <ModelCard
                key={config.id}
                config={config}
                onClick={handleConfigClick}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete model"
        message={`Are you sure you want to delete "${deleteItem?.display_name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Add model dialog */}
      {appId && (
        <CreateModelDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default ModelHub;
