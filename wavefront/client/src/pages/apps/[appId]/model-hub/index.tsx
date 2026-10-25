import { LLM_PROVIDERS_CONFIG } from '@app/config/llm-providers';
import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import ModelCard from '@app/components/ModelCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { useDeleteLLMConfig, useGetLLMConfigs } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateModelDialog from './CreateModelDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const ModelHub: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const deleteLLMConfig = useDeleteLLMConfig(appId);
  const deletion = useDeleteConfirm<LLMInferenceConfig>((item) => deleteLLMConfig.mutateAsync(item.id));
  const { selectedApp } = useDashboardStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [providerFilter, setProviderFilter] = useState('all');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch the models
  const { data: configs = [], isLoading: loading } = useGetLLMConfigs(appId);

  const filteredConfigs = configs.filter(
    (config) =>
      (providerFilter === 'all' || config.type === providerFilter) &&
      matchesSearch(searchTerm, config.id, config.llm_model, config.display_name, config.type)
  );

  const providerOptions = Array.from(new Set(configs.map((config) => config.type)))
    .sort()
    .map((type) => ({ value: type, label: LLM_PROVIDERS_CONFIG[type]?.name ?? type }));

  const handleCreateConfig = () => {
    setCreateDialogOpen(true);
  };

  const handleConfigClick = (modelId: string) => {
    navigate(`/apps/${appId}/model-hub/${modelId}`);
  };

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Model Hub', to: `/apps/${appId}/model-hub` }]} />

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
      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
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
                onDeleteClick={(e, item) => deletion.ask(item, e)}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete model"
        message={`Are you sure you want to delete "${deletion.item?.display_name}"? This action cannot be undone.`}
      />

      {/* Add model dialog */}
      {appId && <CreateModelDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={appId} />}
    </div>
  );
};

export default ModelHub;
