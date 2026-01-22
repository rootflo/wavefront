import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetTtsConfigs } from '@app/hooks';
import { getTtsConfigsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { TtsConfig } from '@app/types/tts-config';
import { useQueryClient } from '@tanstack/react-query';
import { Pencil, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import CreateTtsConfigDialog from './CreateTtsConfigDialog';
import EditTtsConfigDialog from './EditTtsConfigDialog';

const TtsConfigsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<TtsConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<TtsConfig | null>(null);

  // Fetch TTS configs
  const { data: configs = [], isLoading: configsLoading } = useGetTtsConfigs(app);

  const handleDeleteClick = (e: React.MouseEvent, config: TtsConfig) => {
    e.stopPropagation();
    setDeleteItem(config);
  };

  const handleEditClick = (e: React.MouseEvent, config: TtsConfig) => {
    e.stopPropagation();
    setEditItem(config);
  };

  const handleEditSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getTtsConfigsKey(app || '') });
    setEditItem(null);
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.ttsConfigService.deleteTtsConfig(deleteItem.id);
      notifySuccess('TTS configuration deleted successfully');
      queryClient.invalidateQueries({ queryKey: getTtsConfigsKey(app || '') });
      setDeleteItem(null);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete TTS configuration');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateTtsConfig = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getTtsConfigsKey(app || '') });
    setCreateDialogOpen(false);
  };

  const filteredConfigs = configs.filter((config) => {
    const query = searchQuery.toLowerCase();
    return (
      config.display_name.toLowerCase().includes(query) ||
      (config.description && config.description.toLowerCase().includes(query)) ||
      config.provider.toLowerCase().includes(query)
    );
  });

  return (
    <div className="h-full w-full overflow-hidden">
      <div className="w-full">
        <div className="mb-8 flex items-center justify-end">
          <div className="flex items-center gap-4">
            <Input
              type="text"
              placeholder="Search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-[180px]"
            />
            <div className="flex items-center gap-3">
              <Button onClick={handleCreateTtsConfig}>
                <p className="text-sm">Create TTS Config</p>
              </Button>
            </div>
          </div>
        </div>

        {configsLoading ? (
          <div className="flex justify-center py-10">
            <div className="text-gray-500">Loading TTS configurations...</div>
          </div>
        ) : filteredConfigs.length === 0 ? (
          <div className="mt-10 flex justify-center">
            <EmptyStateCard
              title="No TTS configurations found"
              description={
                searchQuery
                  ? 'No TTS configurations match your search.'
                  : 'Get started by creating your first TTS configuration'
              }
              actionText="Create TTS Config"
              onActionClick={handleCreateTtsConfig}
            />
          </div>
        ) : (
          <div className="rounded-md border">
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
                        <Button variant="ghost" size="sm" onClick={(e) => handleDeleteClick(e, config)} title="Delete">
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Delete Confirmation Dialog */}
        <DeleteConfirmationDialog
          isOpen={!!deleteItem}
          title="Delete TTS Configuration"
          message={`Are you sure you want to delete "${deleteItem?.display_name}"? This action cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={handleDeleteCancel}
          loading={deleting}
        />

        {/* Create TTS Config Dialog */}
        {app && (
          <CreateTtsConfigDialog
            isOpen={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            onSuccess={handleCreateSuccess}
          />
        )}

        {/* Edit TTS Config Dialog */}
        {app && editItem && (
          <EditTtsConfigDialog
            isOpen={!!editItem}
            onOpenChange={(open) => !open && setEditItem(null)}
            config={editItem}
            onSuccess={handleEditSuccess}
          />
        )}
      </div>
    </div>
  );
};

export default TtsConfigsPage;
