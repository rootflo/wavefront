import ListHeader from '@app/components/ListHeader';
import DatasourceCard from './DatasourceCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { useDeleteDatasource, useGetAllDatasources } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { Datasource } from '@app/types/datasource';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateDatasourceDialog from './CreateDatasourceDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const DatasourcesManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();

  const [searchTerm, setSearchTerm] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const { data: datasources = [], isLoading: datasourcesLoading } = useGetAllDatasources(appId || '');

  const { selectedApp } = useDashboardStore();
  const navigate = useNavigate();
  const deleteDatasource = useDeleteDatasource(appId);
  const deletion = useDeleteConfirm<Datasource>((item) => deleteDatasource.mutateAsync(item.id));

  const filteredDatasources = datasources.filter((datasource) =>
    matchesSearch(searchTerm, datasource.id, datasource.name, datasource.type)
  );

  const handleCreateDatasource = () => {
    setCreateDialogOpen(true);
  };

  const handleDatasourceClick = (datasourceId: string) => {
    navigate(`/apps/${appId}/datasources/${datasourceId}`);
  };

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Datasources', to: `/apps/${appId}/datasources` }]} />

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
                onDeleteClick={(e, item) => deletion.ask(item, e)}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Datasource"
        message={`Are you sure you want to delete "${deletion.item?.name}"? This action cannot be undone.`}
      />

      {/* Create Datasource Dialog */}
      {appId && <CreateDatasourceDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={appId} />}
    </div>
  );
};

export default DatasourcesManagement;
