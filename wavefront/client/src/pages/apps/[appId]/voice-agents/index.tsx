import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetVoiceAgents } from '@app/hooks';
import { getVoiceAgentsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { VoiceAgent } from '@app/types/voice-agent';
import { getLanguageName } from '@app/constants/languages';
import { useQueryClient } from '@tanstack/react-query';
import { Pencil, Phone, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import CreateVoiceAgentDialog from './CreateVoiceAgentDialog';
import EditVoiceAgentDialog from './EditVoiceAgentDialog';
import OutboundCallDialog from './OutboundCallDialog';

const VoiceAgentsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [deleteItem, setDeleteItem] = useState<VoiceAgent | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<VoiceAgent | null>(null);
  const [callItem, setCallItem] = useState<VoiceAgent | null>(null);

  // Fetch voice agents
  const { data: agents = [], isLoading: agentsLoading } = useGetVoiceAgents(app);

  const handleDeleteClick = (e: React.MouseEvent, agent: VoiceAgent) => {
    e.stopPropagation();
    setDeleteItem(agent);
  };

  const handleEditClick = (e: React.MouseEvent, agent: VoiceAgent) => {
    e.stopPropagation();
    setEditItem(agent);
  };

  const handleCallClick = (e: React.MouseEvent, agent: VoiceAgent) => {
    e.stopPropagation();
    setCallItem(agent);
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
              <Button onClick={handleCreateVoiceAgent}>
                <p className="text-sm">Create Voice Agent</p>
              </Button>
            </div>
          </div>
        </div>

        {agentsLoading ? (
          <div className="flex justify-center py-10">
            <div className="text-gray-500">Loading voice agents...</div>
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
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Inbound #s</TableHead>
                  <TableHead>Outbound #s</TableHead>
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
                    <TableCell className="max-w-md truncate">{agent.description || '-'}</TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-600">{agent.inbound_numbers?.length || 0}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-600">{agent.outbound_numbers?.length || 0}</span>
                    </TableCell>
                    <TableCell>
                      <span
                        className="text-sm text-gray-600"
                        title={agent.supported_languages?.map(getLanguageName).join(', ')}
                      >
                        {agent.supported_languages?.length || 1} ({agent.default_language || 'en'})
                      </span>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-medium ${
                          agent.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {agent.status.toUpperCase()}
                      </span>
                    </TableCell>
                    <TableCell>{new Date(agent.created_at).toLocaleDateString()}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="ghost" size="sm" onClick={(e) => handleEditClick(e, agent)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        {agent.status === 'active' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => handleCallClick(e, agent)}
                            title="Outbound Call"
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

        {/* Delete Confirmation Dialog */}
        <DeleteConfirmationDialog
          isOpen={!!deleteItem}
          title="Delete Voice Agent"
          message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={handleDeleteCancel}
          loading={deleting}
        />

        {/* Create Voice Agent Dialog */}
        {app && (
          <CreateVoiceAgentDialog
            isOpen={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            appId={app}
            onSuccess={handleCreateSuccess}
          />
        )}

        {/* Edit Voice Agent Dialog */}
        {app && editItem && (
          <EditVoiceAgentDialog
            isOpen={!!editItem}
            onOpenChange={(open) => !open && setEditItem(null)}
            appId={app}
            agent={editItem}
            onSuccess={handleEditSuccess}
          />
        )}

        {/* Outbound Call Dialog */}
        {app && callItem && (
          <OutboundCallDialog
            isOpen={!!callItem}
            onOpenChange={(open) => !open && setCallItem(null)}
            agent={callItem}
          />
        )}
      </div>
    </div>
  );
};

export default VoiceAgentsPage;
