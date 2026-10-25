import ListHeader from '@app/components/ListHeader';
import ApiServiceCard from '@app/components/ApiServiceCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { useDeleteApiService, useGetApiServices } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { ApiServiceItem } from '@app/types/api-service';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateApiServiceDialog from './CreateApiServiceDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const ApiServiceManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const deleteApiService = useDeleteApiService(appId);
  const deletion = useDeleteConfirm<ApiServiceItem>((item) => deleteApiService.mutateAsync(item.service_id));
  const [searchTerm, setSearchTerm] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { selectedApp } = useDashboardStore();

  const { data: apiServices = [], isLoading: loading } = useGetApiServices(appId);

  const filteredApiServices = apiServices.filter((service) =>
    matchesSearch(searchTerm, service.name, service.service_id)
  );

  const handleCreateApiService = () => {
    setCreateDialogOpen(true);
  };

  const handleApiServiceClick = (serviceId: string) => {
    navigate(`/apps/${appId}/api-services/${serviceId}`);
  };

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'API Services', to: `/apps/${appId}/api-services` }]} />

      <ListHeader
        title="API Services"
        count={filteredApiServices.length || undefined}
        subtitle={<>Manage API Connectors for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search api services' }}
        primary={{ label: 'Create service', onClick: handleCreateApiService }}
      />
      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
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
                onDeleteClick={(e, item) => deletion.ask(item, e)}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete API Service"
        message={`Are you sure you want to delete "${
          deletion.item?.name || deletion.item?.service_id
        }"? This action cannot be undone.`}
      />

      {/* Create API Service Dialog */}
      {appId && <CreateApiServiceDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={appId} />}
    </div>
  );
};

export default ApiServiceManagement;
