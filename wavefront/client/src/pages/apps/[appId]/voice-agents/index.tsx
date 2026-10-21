import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetVoiceAgents } from '@app/hooks';
import { getVoiceAgentsKey } from '@app/hooks/data/query-keys';
import { copyToClipboard, extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { VoiceAgent, VoiceAgentListItem } from '@app/types/voice-agent';
import { getLanguageName } from '@app/constants/languages';
import { useQueryClient } from '@tanstack/react-query';
import { Copy, Pencil, Phone, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import CreateVoiceAgentDialog from './CreateVoiceAgentDialog';
import EditVoiceAgentDialog from './EditVoiceAgentDialog';
import VoiceAgentOperationsDialog from './VoiceAgentOperationsDialog';

const VoiceAgentsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<VoiceAgentListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<VoiceAgent | null>(null);
  const [opsItem, setOpsItem] = useState<VoiceAgentListItem | null>(null);
  const [editLoadingId, setEditLoadingId] = useState<string | null>(null);

  const { data: agents = [], isLoading: agentsLoading } = useGetVoiceAgents(app);

  const fetchAgentDetail = async (agentId: string): Promise<VoiceAgent | null> => {
    setEditLoadingId(agentId);
    try {
      const response = await floConsoleService.voiceAgentService.getVoiceAgent(agentId);
      const detail = response.data?.data;
      if (!detail) {
        notifyError('Failed to load voice agent details');
        return null;
      }
      return detail;
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to load voice agent details');
      return null;
    } finally {
      setEditLoadingId(null);
    }
  };

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const handleDeleteClick = (e: React.MouseEvent, agent: VoiceAgentListItem) => {
    e.stopPropagation();
    setDeleteItem(agent);
  };

  const handleEditClick = async (e: React.MouseEvent, agent: VoiceAgentListItem) => {
    e.stopPropagation();
    const detail = await fetchAgentDetail(agent.id);
    if (detail) setEditItem(detail);
  };

  const handleOperationsClick = (e: React.MouseEvent, agent: VoiceAgentListItem) => {
    e.stopPropagation();
    setOpsItem(agent);
  };

  const handleEditSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getVoiceAgentsKey(app || '') });
    setEditItem(null);
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.voiceAgentService.deleteVoiceAgent(deleteItem.id);
      notifySuccess('Voice agent deleted successfully');
      queryClient.invalidateQueries({ queryKey: getVoiceAgentsKey(app || '') });
      setDeleteItem(null);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to delete voice agent');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateVoiceAgent = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({ queryKey: getVoiceAgentsKey(app || '') });
    setCreateDialogOpen(false);
  };

  const filteredAgents = agents.filter((agent) => {
    const query = searchQuery.toLowerCase();
    return (
      agent.name.toLowerCase().includes(query) ||
      (agent.description && agent.description.toLowerCase().includes(query)) ||
      agent.status.toLowerCase().includes(query)
    );
  });

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <div className="mb-6 flex shrink-0 items-center justify-end">
        <div className="flex items-center gap-4">
          <Input
            type="text"
            placeholder="Search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-[180px]"
          />
          <div className="flex items-center gap-3">
            <Button onClick={handleCreateVoiceAgent}>
              <p className="text-sm">Create Voice Agent</p>
            </Button>
          </div>
        </div>
      </div>

      {agentsLoading ? (
        <div className="flex justify-center py-10">
          <div className="frost-text-muted">Loading voice agents...</div>
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No voice agents found"
            description={
              searchQuery ? 'No voice agents match your search.' : 'Get started by creating your first voice agent'
            }
            actionText="Create Voice Agent"
            onActionClick={handleCreateVoiceAgent}
          />
        </div>
      ) : (
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Languages</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredAgents.map((agent) => (
                <TableRow key={agent.id}>
                  <TableCell className="font-medium">{agent.name}</TableCell>
                  <TableCell className="max-w-[260px]" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1">
                      <span className="truncate font-mono text-xs" title={agent.id}>
                        {agent.id}
                      </span>
                      <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(agent.id)}>
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell className="max-w-md truncate">{agent.description || '-'}</TableCell>
                  <TableCell>
                    <span
                      className="frost-text-muted text-sm"
                      title={agent.supported_languages?.map(getLanguageName).join(', ')}
                    >
                      {agent.supported_languages?.length || 1} ({agent.default_language || 'en'})
                    </span>
                  </TableCell>
                  <TableCell>
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        agent.status === 'active'
                          ? 'bg-emerald-400/15 text-emerald-700 dark:text-emerald-400'
                          : 'bg-frost-glass-strong frost-text-muted'
                      }`}
                    >
                      {agent.status.toUpperCase()}
                    </span>
                  </TableCell>
                  <TableCell>{new Date(agent.created_at).toLocaleDateString()}</TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => void handleEditClick(e, agent)}
                        title="Edit"
                        disabled={editLoadingId === agent.id}
                        loading={editLoadingId === agent.id}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      {agent.status === 'active' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleOperationsClick(e, agent)}
                          title="Talk to agent"
                        >
                          <Phone className="h-4 w-4" />
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={(e) => handleDeleteClick(e, agent)} title="Delete">
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

      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Voice Agent"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {app && (
        <CreateVoiceAgentDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={app}
          onSuccess={handleCreateSuccess}
        />
      )}

      {app && editItem && (
        <EditVoiceAgentDialog
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          appId={app}
          agent={editItem}
          onSuccess={handleEditSuccess}
        />
      )}

      {app && opsItem && (
        <VoiceAgentOperationsDialog
          isOpen={!!opsItem}
          onOpenChange={(open) => !open && setOpsItem(null)}
          agentSummary={opsItem}
          appId={app}
        />
      )}
    </div>
  );
};

export default VoiceAgentsPage;
