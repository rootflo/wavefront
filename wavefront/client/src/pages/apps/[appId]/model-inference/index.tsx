import floConsoleService from '@app/api';
import { ModelData } from '@app/api/model-inference-service';
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
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { useGetModels } from '@app/hooks';
import { getModelsKey } from '@app/hooks/data/query-keys';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateModelInferenceDialog from './CreateModelInferenceDialog';
import { Alert, AlertDescription, AlertTitle } from '@app/components/ui/alert';

const ModelManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteItem, setDeleteItem] = useState<ModelData | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  // Fetch models
  const { data: models = [], isLoading: loading } = useGetModels(appId);

  const filteredModels = models.filter(
    (model) =>
      model.model_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      model.model_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      model.model_type.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateModel = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getModelsKey(appId || '') });
    setCreateDialogOpen(false);
  };

  const handleModelClick = (modelId: string) => {
    navigate(`/apps/${appId}/model-inference/${modelId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, model: ModelData) => {
    e.stopPropagation();
    setDeleteItem(model);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.modelInferenceService.deleteModel(deleteItem.model_id);
      notifySuccess('Model deleted successfully');
      queryClient.invalidateQueries({ queryKey: getModelsKey(appId || '') });
      setDeleteItem(null);
    } catch (error) {
      console.error('Error deleting model:', error);
      let errorMessage = 'Failed to delete model';

      if (error && typeof error === 'object' && 'response' in error) {
        const response = (
          error as {
            response: {
              data?: { meta?: { error?: string }; message?: string };
            };
          }
        ).response;
        if (response?.data?.meta?.error) {
          errorMessage = response.data.meta.error;
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
                onClick={() => navigate(`/apps/${appId}/model-inference`)}
                className="hover:text-foreground cursor-pointer"
              >
                Models
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">Model Inference</h1>
          <p className="animate-fade-in mt-2 text-gray-600">Manage models for {selectedApp?.app_name}</p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Button onClick={handleCreateModel}>Upload Model</Button>
        </div>
      </div>
      <div>
        <Alert variant="info">
          <AlertTitle> Coming soon</AlertTitle>
          <AlertDescription>This feature is currently in alpha and is not ready for production.</AlertDescription>
        </Alert>
      </div>
      <div className="grid gap-6 overflow-y-auto py-2 sm:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={2} />
            ))}
          </>
        ) : filteredModels.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No models found"
              description="Get started by uploading your first model"
              actionText="Upload Model"
              onActionClick={handleCreateModel}
            />
          </div>
        ) : (
          <>
            {filteredModels.map((model) => (
              <ModelCard
                key={model.model_id}
                model={model}
                onClick={handleModelClick}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Model"
        message={`Are you sure you want to delete "${
          deleteItem?.model_name || deleteItem?.model_id
        }"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Model Dialog */}
      {appId && (
        <CreateModelInferenceDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default ModelManagement;
