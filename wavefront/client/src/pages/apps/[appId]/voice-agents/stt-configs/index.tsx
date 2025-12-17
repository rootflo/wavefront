import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetSttConfigs } from '@app/hooks';
import { getSttConfigsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { SttConfig } from '@app/types/stt-config';
import { useQueryClient } from '@tanstack/react-query';
import { Pencil, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import CreateSttConfigDialog from './CreateSttConfigDialog';
import EditSttConfigDialog from './EditSttConfigDialog';

const SttConfigsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<SttConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<SttConfig | null>(null);

  // Fetch STT configs
  const { data: configs = [], isLoading: configsLoading } = useGetSttConfigs(app);

  const handleDeleteClick = (e: React.MouseEvent, config: SttConfig) => {
    e.stopPropagation();
    setDeleteItem(config);
  };

  const handleEditClick = (e: React.MouseEvent, config: SttConfig) => {
    e.stopPropagation();
    setEditItem(config);
  };

  const handleEditSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getSttConfigsKey(app || '') });
    setEditItem(null);
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.sttConfigService.deleteSttConfig(deleteItem.id);
      notifySuccess('STT configuration deleted successfully');
      queryClient.invalidateQueries({ queryKey: getSttConfigsKey(app || '') });
      setDeleteItem(null);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete STT configuration');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateSttConfig = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getSttConfigsKey(app || '') });
    setCreateDialogOpen(false);
  };

  const filteredConfigs = configs.filter((config) => {
    const query = searchQuery.toLowerCase();
    return (
      config.display_name.toLowerCase().includes(query) ||
      (config.description && config.description.toLowerCase().includes(query)) ||
      config.provider.toLowerCase().includes(query) ||
      (config.language && config.language.toLowerCase().includes(query))
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
              <Button onClick={handleCreateSttConfig}>
                <p className="text-sm">Create STT Config</p>
              </Button>
            </div>
          </div>
        </div>

        {configsLoading ? (
          <div className="flex justify-center py-10">
            <div className="text-gray-500">Loading STT configurations...</div>
          </div>
        ) : filteredConfigs.length === 0 ? (
          <div className="mt-10 flex justify-center">
            <EmptyStateCard
              title="No STT configurations found"
              description={
                searchQuery
                  ? 'No STT configurations match your search.'
                  : 'Get started by creating your first STT configuration'
              }
              actionText="Create STT Config"
              onActionClick={handleCreateSttConfig}
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
                  <TableHead>Language</TableHead>
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
                    <TableCell>{config.language || '-'}</TableCell>
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
          title="Delete STT Configuration"
          message={`Are you sure you want to delete "${deleteItem?.display_name}"? This action cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={handleDeleteCancel}
          loading={deleting}
        />

        {/* Create STT Config Dialog */}
        {app && (
          <CreateSttConfigDialog
            isOpen={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            onSuccess={handleCreateSuccess}
          />
        )}

        {/* Edit STT Config Dialog */}
        {app && editItem && (
          <EditSttConfigDialog
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

export default SttConfigsPage;
