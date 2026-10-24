import ListHeader from '@app/components/ListHeader';
import floConsoleService from '@app/api';
import DatasourceCard from '@app/components/DatasourceCard';
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
import { getAllDatasourcesKey, useGetAllDatasources } from '@app/hooks';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { Datasource } from '@app/types/datasource';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateDatasourceDialog from './CreateDatasourceDialog';

const DatasourcesManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();

  const [searchTerm, setSearchTerm] = useState('');
  const [deleteItem, setDeleteItem] = useState<Datasource | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const { data: datasources = [], isLoading: datasourcesLoading } = useGetAllDatasources(appId || '');

  const { selectedApp } = useDashboardStore();
  const navigate = useNavigate();
  const { notifySuccess } = useNotifyStore();
  const queryClient = useQueryClient();

  const filteredDatasources = datasources.filter(
    (datasource) =>
      datasource.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      datasource.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      datasource.type.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateDatasource = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    setCreateDialogOpen(false);
  };

  const handleDatasourceClick = (datasourceId: string) => {
    navigate(`/apps/${appId}/datasources/${datasourceId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, datasource: Datasource) => {
    e.stopPropagation(); // Prevent triggering the click handler for the card
    setDeleteItem(datasource);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;
    setDeleting(true);
    try {
      await floConsoleService.datasourcesService.deleteDatasource(deleteItem.id);
      queryClient.invalidateQueries({
        queryKey: getAllDatasourcesKey(appId || ''),
      });

      notifySuccess('Datasource deleted successfully');
      setDeleteItem(null);
    } catch (error) {
      console.error('Error deleting datasource:', error);
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
                onClick={() => navigate(`/apps/${appId}/datasources`)}
                className="hover:text-foreground cursor-pointer"
              >
                Datasources
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <ListHeader
        title="Datasources"
        count={filteredDatasources.length || undefined}
        subtitle={<>Manage data connections for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search datasources' }}
        primary={{ label: 'Create datasource', onClick: handleCreateDatasource }}
      />
      <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
        {datasourcesLoading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} showDescription metadataCount={3} />
            ))}
          </>
        ) : filteredDatasources.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No datasources found"
              description="Get started by creating your first datasource to connect to external data sources"
              actionText="Create Data Source"
              onActionClick={handleCreateDatasource}
            />
          </div>
        ) : (
          <>
            {filteredDatasources.map((datasource) => (
              <DatasourceCard
                key={datasource.id}
                datasource={datasource}
                onClick={handleDatasourceClick}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Datasource"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Datasource Dialog */}
      {appId && (
        <CreateDatasourceDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default DatasourcesManagement;
