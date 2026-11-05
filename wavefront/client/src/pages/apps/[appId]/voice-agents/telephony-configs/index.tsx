import ListHeader from '@app/components/ListHeader';
import ResourceCard from '@app/components/ResourceCard';
import ResourceList, { ListViewToggle, ResourceListSkeleton } from '@app/components/ResourceList';
import { useListView } from '@app/lib/list-view';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useDeleteTelephonyConfig, useGetTelephonyConfigs } from '@app/hooks';
import { TelephonyConfig } from '@app/types/telephony-config';
import { Pencil, Trash2, PhoneCall } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import TelephonyConfigFormDialog from './TelephonyConfigFormDialog';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const TelephonyConfigsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const [view, setView] = useListView('telephony-configs');
  const deleteConfig = useDeleteTelephonyConfig(app);
  const deletion = useDeleteConfirm<TelephonyConfig>((item) => deleteConfig.mutateAsync(item.id));

  const [searchQuery, setSearchQuery] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<TelephonyConfig | null>(null);

  // Fetch telephony configs
  const { data: configs = [], isLoading: configsLoading } = useGetTelephonyConfigs(app);

  const handleEditClick = (e: React.MouseEvent, config: TelephonyConfig) => {
    e.stopPropagation();
    setEditItem(config);
  };

  const handleCreateTelephonyConfig = () => {
    setCreateDialogOpen(true);
  };

  const filteredConfigs = configs.filter((config) =>
    matchesSearch(searchQuery, config.display_name, config.description, config.provider, config.connection_type)
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden max-md:overflow-y-auto">
      <ListHeader
        extras={<ListViewToggle view={view} onChange={setView} />}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search' }}
        primary={{ label: 'Create telephony config', onClick: handleCreateTelephonyConfig }}
        className="md:justify-end"
      />

      {configsLoading ? (
        <ResourceListSkeleton view={view} />
      ) : filteredConfigs.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No telephony configurations found"
            description={
              searchQuery
                ? 'No telephony configurations match your search.'
                : 'Get started by creating your first telephony configuration'
            }
            actionText="Create Telephony Config"
            onActionClick={handleCreateTelephonyConfig}
          />
        </div>
      ) : (
        <ResourceList
          view={view}
          cards={
            <>
              {filteredConfigs.map((config) => (
                <ResourceCard
                  key={config.id}
                  icon={PhoneCall}
                  title={config.display_name}
                  description={config.description || undefined}
                  metadata={[
                    { label: 'Provider', value: config.provider },
                    { label: 'Connection type', value: config.connection_type },
                    { label: 'Created', value: new Date(config.created_at).toLocaleDateString() },
                  ]}
                  onEditClick={(e) => handleEditClick(e, config)}
                  onDeleteClick={(e) => deletion.ask(config, e)}
                  deleteTitle="Delete config"
                />
              ))}
            </>
          }
          table={
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Display Name</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>Connection Type</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredConfigs.map((config) => (
                  <TableRow key={config.id}>
                    <TableCell className="font-medium">{config.display_name}</TableCell>
                    <TableCell>{config.provider}</TableCell>
                    <TableCell>{config.connection_type}</TableCell>
                    <TableCell className="max-w-md truncate">{config.description || '-'}</TableCell>
                    <TableCell>{new Date(config.created_at).toLocaleDateString()}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="ghost" size="sm" onClick={(e) => handleEditClick(e, config)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={(e) => deletion.ask(config, e)} title="Delete">
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          }
        />
      )}

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Telephony Configuration"
        message={`Are you sure you want to delete "${deletion.item?.display_name}"? This action cannot be undone.`}
      />

      {/* Create Telephony Config Dialog */}
      {app && <TelephonyConfigFormDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} />}

      {/* Edit Telephony Config Dialog */}
      {app && editItem && (
        <TelephonyConfigFormDialog
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          config={editItem}
        />
      )}
    </div>
  );
};

export default TelephonyConfigsPage;
