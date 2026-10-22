import ListHeader from '@app/components/ListHeader';
import ResourceCard from '@app/components/ResourceCard';
import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { Badge } from '@app/components/ui/badge';
import { useGetVoiceAgentTools } from '@app/hooks';
import { getVoiceAgentToolsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { VoiceAgentTool } from '@app/types/tool';
import { useQueryClient } from '@tanstack/react-query';
import { Pencil, Trash2, Wrench } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import CreateToolDialog from './CreateToolDialog';
import EditToolDialog from './EditToolDialog';

const ToolsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<VoiceAgentTool | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<VoiceAgentTool | null>(null);

  // Fetch tools
  const { data: tools = [], isLoading: toolsLoading, isError, error } = useGetVoiceAgentTools(app);

  const handleDeleteClick = (e: React.MouseEvent, tool: VoiceAgentTool) => {
    e.stopPropagation();
    setDeleteItem(tool);
  };

  const handleEditClick = (e: React.MouseEvent, tool: VoiceAgentTool) => {
    e.stopPropagation();
    setEditItem(tool);
  };

  const handleEditSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getVoiceAgentToolsKey(app || '') });
    setEditItem(null);
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.toolService.deleteTool(deleteItem.id);
      notifySuccess('Tool deleted successfully');
      queryClient.invalidateQueries({ queryKey: getVoiceAgentToolsKey(app || '') });
      setDeleteItem(null);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete tool');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateTool = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getVoiceAgentToolsKey(app || '') });
    setCreateDialogOpen(false);
  };

  const filteredTools = tools.filter((tool) => {
    const query = searchQuery.toLowerCase();
    return (
      tool.name.toLowerCase().includes(query) ||
      tool.display_name.toLowerCase().includes(query) ||
      (tool.description && tool.description.toLowerCase().includes(query)) ||
      tool.tool_type.toLowerCase().includes(query)
    );
  });

  const getToolTypeColor = (type: string) => {
    if (type === 'api') return 'bg-blue-100 text-blue-800';
    if (type === 'app') return 'bg-emerald-100 text-emerald-800';
    return 'bg-purple-100 text-purple-800';
  };

  const getApiMethod = (tool: VoiceAgentTool) => {
    if (tool.tool_type === 'api' && tool.config && 'method' in tool.config) {
      return tool.config.method;
    }
    return '-';
  };

  const getApiUrl = (tool: VoiceAgentTool) => {
    if (tool.tool_type === 'api' && tool.config && 'url' in tool.config) {
      return tool.config.url;
    }
    return '-';
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden max-md:overflow-y-auto">
      <ListHeader
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search' }}
        primary={{ label: 'Create tool', onClick: handleCreateTool }}
        className="md:justify-end"
      />

      {isError ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="Error loading tools"
            description={extractErrorMessage(error) || 'Failed to fetch voice agent tools. Please try again.'}
            actionText="Retry"
            onActionClick={() => queryClient.invalidateQueries({ queryKey: getVoiceAgentToolsKey(app || '') })}
          />
        </div>
      ) : toolsLoading ? (
        <div className="flex justify-center py-10">
          <div className="frost-text-muted">Loading tools...</div>
        </div>
      ) : filteredTools.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No tools found"
            description={
              searchQuery ? 'No tools match your search.' : 'Get started by creating your first tool for voice agents'
            }
            actionText="Create Tool"
            onActionClick={handleCreateTool}
          />
        </div>
      ) : (
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1 max-md:flex-none">
          <div data-mobile-cards className="flex flex-col gap-3 pb-24 md:hidden">
            {filteredTools.map((tool) => (
              <ResourceCard
                key={tool.id}
                icon={Wrench}
                title={tool.display_name}
                description={tool.description || undefined}
                metadata={[
                  { label: 'Name', value: tool.name },
                  { label: 'Type', value: tool.tool_type.toUpperCase(), className: getToolTypeColor(tool.tool_type) },
                  ...(getApiMethod(tool) ? [{ label: 'Method', value: getApiMethod(tool), isMono: true }] : []),
                  ...(getApiUrl(tool) ? [{ label: 'URL', value: getApiUrl(tool), isMono: true }] : []),
                ]}
                onEditClick={(e) => handleEditClick(e, tool)}
                onDeleteClick={(e) => handleDeleteClick(e, tool)}
                deleteTitle="Delete tool"
              />
            ))}
          </div>
          <div className="max-md:hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Display Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTools.map((tool) => (
                  <TableRow key={tool.id}>
                    <TableCell className="text-sm">{tool.name}</TableCell>
                    <TableCell className="font-medium">{tool.display_name}</TableCell>
                    <TableCell>
                      <Badge className={getToolTypeColor(tool.tool_type)}>{tool.tool_type.toUpperCase()}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{getApiMethod(tool)}</TableCell>
                    <TableCell className="max-w-xs truncate text-xs">{getApiUrl(tool)}</TableCell>
                    <TableCell className="max-w-md truncate">{tool.description || '-'}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="ghost" size="sm" onClick={(e) => handleEditClick(e, tool)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={(e) => handleDeleteClick(e, tool)} title="Delete">
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Tool"
        message={`Are you sure you want to delete "${deleteItem?.display_name}"? This will also detach it from all voice agents.`}
        onConfirm={handleDelete}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Tool Dialog */}
      {app && (
        <CreateToolDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          onSuccess={handleCreateSuccess}
        />
      )}

      {/* Edit Tool Dialog */}
      {app && editItem && (
        <EditToolDialog
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          tool={editItem}
          onSuccess={handleEditSuccess}
        />
      )}
    </div>
  );
};

export default ToolsPage;
