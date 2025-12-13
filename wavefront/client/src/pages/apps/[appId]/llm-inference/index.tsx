import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import LLMConfigCard from '@app/components/LLMConfigCard';
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
import { useGetLLMConfigs } from '@app/hooks';
import { getLLMConfigsKey } from '@app/hooks/data/query-keys';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateLLMInferenceDialog from './CreateLLMInferenceDialog';

const LLMInferenceConfigsManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [deleteItem, setDeleteItem] = useState<LLMInferenceConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch LLM configs
  const { data: configs = [], isLoading: loading } = useGetLLMConfigs(appId);

  const filteredConfigs = configs.filter(
    (config) =>
      config.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      config.llm_model.toLowerCase().includes(searchTerm.toLowerCase()) ||
      config.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      config.type.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateConfig = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getLLMConfigsKey(appId || '') });
    setCreateDialogOpen(false);
  };

  const handleConfigClick = (llmId: string) => {
    navigate(`/apps/${appId}/llm-repository/${llmId}`);
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
      console.error('Error deleting LLM inference config:', error);

      let errorMessage = 'Failed to delete model';
      if (error && typeof error === 'object' && 'response' in error) {
        const response = (error as any).response;
        if (response?.data?.error) {
          errorMessage = response.data.error;
        } else if (response?.data?.message) {
          errorMessage = response.data.message;
        }
      }

      notifyError(errorMessage);
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
                onClick={() => navigate(`/apps/${appId}/llm-repository`)}
                className="hover:text-foreground cursor-pointer"
              >
                LLM Repository
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">LLM Repository</h1>
          <p className="animate-fade-in mt-2 text-gray-600">Manage LLMs for {selectedApp?.app_name}</p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Button onClick={handleCreateConfig}>Add LLM</Button>
        </div>
      </div>
      <div className="grid gap-6 overflow-y-auto py-2 sm:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={4} />
            ))}
          </>
        ) : filteredConfigs.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No LLMs found"
              description="Get started by adding your first LLM to the repository"
              actionText="Add LLM"
              onActionClick={handleCreateConfig}
            />
          </div>
        ) : (
          <>
            {filteredConfigs.map((config) => (
              <LLMConfigCard
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
        title="Delete LLM"
        message={`Are you sure you want to delete "${deleteItem?.display_name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create LLM Dialog */}
      {appId && (
        <CreateLLMInferenceDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default LLMInferenceConfigsManagement;
