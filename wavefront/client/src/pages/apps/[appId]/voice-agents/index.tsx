import ListHeader from '@app/components/ListHeader';
import ResourceCard from '@app/components/ResourceCard';
import ResourceList, { ListViewToggle, ResourceListSkeleton } from '@app/components/ResourceList';
import { useListView } from '@app/lib/list-view';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useDeleteVoiceAgent, useGetVoiceAgents } from '@app/hooks';
import { copyToClipboard } from '@app/utils/clipboard';
import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { VoiceAgent, VoiceAgentListItem } from '@app/types/voice-agent';
import { getLanguageName } from '@app/constants/languages';
import { Copy, Pencil, Phone, Trash2, Mic } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import VoiceAgentFormDialog from './VoiceAgentFormDialog';
import VoiceAgentOperationsDialog from './VoiceAgentOperationsDialog';
import floConsoleService from '@app/api';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const VoiceAgentsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const [view, setView] = useListView('voice-agents');
  const deleteVoiceAgent = useDeleteVoiceAgent(app);
  const deletion = useDeleteConfirm<VoiceAgentListItem>((item) => deleteVoiceAgent.mutateAsync(item.id));
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
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

  const handleEditClick = async (e: React.MouseEvent, agent: VoiceAgentListItem) => {
    e.stopPropagation();
    const detail = await fetchAgentDetail(agent.id);
    if (detail) setEditItem(detail);
  };

  const handleOperationsClick = (e: React.MouseEvent, agent: VoiceAgentListItem) => {
    e.stopPropagation();
    setOpsItem(agent);
  };

  const handleCreateVoiceAgent = () => {
    setCreateDialogOpen(true);
  };

  const filteredAgents = agents.filter((agent) =>
    matchesSearch(searchQuery, agent.name, agent.description, agent.status)
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden max-md:overflow-y-auto">
      <ListHeader
        extras={<ListViewToggle view={view} onChange={setView} />}
        search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search' }}
        primary={{ label: 'Create voice agent', onClick: handleCreateVoiceAgent }}
        className="md:justify-end"
      />

      {agentsLoading ? (
        <ResourceListSkeleton view={view} />
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
        <ResourceList
          view={view}
          cards={
            <>
              {filteredAgents.map((agent) => (
                <ResourceCard
                  key={agent.id}
                  icon={Mic}
                  title={agent.name}
                  description={agent.description || undefined}
                  metadata={[
                    { label: 'Id', value: agent.id, isMono: true, isCopyable: true },
                    {
                      label: 'Status',
                      value: agent.status.toUpperCase(),
                      className:
                        agent.status === 'active'
                          ? 'bg-emerald-400/15 text-emerald-700 dark:text-emerald-400'
                          : 'bg-frost-glass-strong frost-text-muted',
                    },
                    {
                      label: 'Languages',
                      value: `${agent.supported_languages?.length || 1} (${agent.default_language || 'en'})`,
                    },
                    { label: 'Created', value: new Date(agent.created_at).toLocaleDateString() },
                  ]}
                  onEditClick={(e) => void handleEditClick(e, agent)}
                  onDeleteClick={(e) => deletion.ask(agent, e)}
                  deleteTitle="Delete voice agent"
                  extraActions={
                    agent.status === 'active'
                      ? [{ label: 'Talk to agent', icon: Phone, onClick: (e) => handleOperationsClick(e, agent) }]
                      : []
                  }
                />
              ))}
            </>
          }
          table={
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
                        <Button variant="ghost" size="sm" onClick={(e) => deletion.ask(agent, e)} title="Delete">
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

      <DeleteConfirmationDialog
        {...deletion.dialogProps}
        title="Delete Voice Agent"
        message={`Are you sure you want to delete "${deletion.item?.name}"? This action cannot be undone.`}
      />

      {app && <VoiceAgentFormDialog isOpen={createDialogOpen} onOpenChange={setCreateDialogOpen} appId={app} />}

      {app && editItem && (
        <VoiceAgentFormDialog
          isOpen={!!editItem}
          onOpenChange={(open) => !open && setEditItem(null)}
          appId={app}
          agent={editItem}
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
