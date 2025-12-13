import floConsoleService from '@app/api';
import ApiServiceCard from '@app/components/ApiServiceCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
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
import { useGetApiServices } from '@app/hooks';
import { getApiServicesKey } from '@app/hooks/data/query-keys';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { ApiServiceItem } from '@app/types/api-service';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateApiServiceDialog from './CreateApiServiceDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';

const ApiServiceManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteItem, setDeleteItem] = useState<ApiServiceItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { selectedApp } = useDashboardStore();
  const { notifySuccess, notifyError } = useNotifyStore();

  const { data: apiServices = [], isLoading: loading } = useGetApiServices(appId);

  const filteredApiServices = apiServices.filter(
    (service) =>
      (service.name || service.service_id).toLowerCase().includes(searchTerm.toLowerCase()) ||
      service.service_id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateApiService = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getApiServicesKey(appId || '') });
    setCreateDialogOpen(false);
  };

  const handleApiServiceClick = (serviceId: string) => {
    navigate(`/apps/${appId}/api-services/${serviceId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, service: ApiServiceItem) => {
    e.stopPropagation();
    setDeleteItem(service);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.apiServiceService.deleteApiService(deleteItem.service_id);
      notifySuccess('API Service deleted successfully');
      queryClient.invalidateQueries({
        queryKey: getApiServicesKey(appId || ''),
      });
      setDeleteItem(null);
    } catch (error) {
      console.error('Error deleting API service:', error);
      notifyError('Failed to delete API service');
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
                onClick={() => navigate(`/apps/${appId}/api-services`)}
                className="hover:text-foreground cursor-pointer"
              >
                API Services
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="animate-fade-in text-3xl font-bold text-gray-900">API Services</h1>
          <p className="animate-fade-in mt-2 text-gray-600">Manage API Connectors for {selectedApp?.app_name}</p>
        </div>
        <div className="animate-fade-in flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Button onClick={handleCreateApiService}>Create Service</Button>
        </div>
      </div>
      <div className="grid gap-6 overflow-y-auto py-2 sm:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 20 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={2} />
            ))}
          </>
        ) : filteredApiServices.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No API services found"
              description="Get started by creating your first API service"
              actionText="Create Service"
              onActionClick={() => setCreateDialogOpen(true)}
            />
          </div>
        ) : (
          <>
            {filteredApiServices.map((service) => (
              <ApiServiceCard
                key={service.service_id}
                service={service}
                onClick={handleApiServiceClick}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete API Service"
        message={`Are you sure you want to delete "${
          deleteItem?.name || deleteItem?.service_id
        }"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create API Service Dialog */}
      {appId && (
        <CreateApiServiceDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default ApiServiceManagement;
