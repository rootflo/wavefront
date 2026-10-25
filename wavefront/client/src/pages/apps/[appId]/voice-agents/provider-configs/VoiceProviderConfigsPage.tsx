import ListHeader from '@app/components/ListHeader';
import ResourceCard from '@app/components/ResourceCard';
import ResourceList, { ListViewToggle, ResourceListSkeleton } from '@app/components/ResourceList';
import { useListView } from '@app/lib/list-view';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { VoiceProviderKind, useDeleteVoiceProviderConfig, useGetSttConfigs, useGetTtsConfigs } from '@app/hooks';
import { Pencil, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import { VOICE_PROVIDER_KINDS } from './kinds';
import VoiceProviderConfigFormDialog, { VoiceProviderConfig } from './VoiceProviderConfigFormDialog';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

/** The STT and TTS config list pages: identical apart from the provider kind. */
const VoiceProviderConfigsPage: React.FC<{ kind: VoiceProviderKind }> = ({ kind }) => {
  const { app } = useParams<{ app: string }>();
  const [view, setView] = useListView(`${kind}-configs`);
  const deleteConfig = useDeleteVoiceProviderConfig(kind, app);
  const deletion = useDeleteConfirm<VoiceProviderConfig>((item) => deleteConfig.mutateAsync(item.id));
  const { label, icon } = VOICE_PROVIDER_KINDS[kind];

  const [searchQuery, setSearchQuery] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<VoiceProviderConfig | null>(null);

  // Only the query for this page's kind is enabled
  const sttConfigs = useGetSttConfigs(kind === 'stt' ? app : undefined);
  const ttsConfigs = useGetTtsConfigs(kind === 'tts' ? app : undefined);
  const { data: configs = [], isLoading: configsLoading } = kind === 'stt' ? sttConfigs : ttsConfigs;

  const handleEditClick = (e: React.MouseEvent, config: VoiceProviderConfig) => {
    e.stopPropagation();
    setEditItem(config);
  };

  const handleCreateConfig = () => {
    setCreateDialogOpen(true);
  };

  const filteredConfigs = configs.filter((config) =>
    matchesSearch(searchQuery, config.display_name, config.description, config.provider)
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden max-md:overflow-y-auto">
      <ListHeader
        extras={<ListViewToggle view={view} onChange={setView} />}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search' }}
        primary={{ label: `Create ${label} config`, onClick: handleCreateConfig }}
        className="md:justify-end"
      />

      {configsLoading ? (
        <ResourceListSkeleton view={view} />
      ) : filteredConfigs.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title={`No ${label} configurations found`}
            description={
              searchQuery
                ? `No ${label} configurations match your search.`
                : `Get started by creating your first ${label} configuration`
            }
            actionText={`Create ${label} Config`}
            onActionClick={handleCreateConfig}
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
                  icon={icon}
                  title={config.display_name}
                  description={config.description || undefined}
                  metadata={[
                    { label: 'Provider', value: config.provider },
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
        title={`Delete ${label} Configuration`}
        message={`Are you sure you want to delete "${deletion.item?.display_name}"? This action cannot be undone.`}
      />

      {app && (
        <VoiceProviderConfigFormDialog kind={kind} isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} />
      )}

      {app && editItem && (
        <VoiceProviderConfigFormDialog
          kind={kind}
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          config={editItem}
        />
      )}
    </div>
  );
};

export default VoiceProviderConfigsPage;
