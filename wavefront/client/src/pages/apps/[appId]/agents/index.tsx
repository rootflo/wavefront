import AgentCard from '@app/components/AgentCard';
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
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useDeleteAgent, useGetAgents, useGetNamespaces } from '@app/hooks';
import { useDashboardStore } from '@app/store';
import { AgentListItem } from '@app/types/agent';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateAgentDialog from './CreateAgentDialog';

const AgentManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [namespace, setNamespace] = useState('');
  const [deleteItem, setDeleteItem] = useState<AgentListItem | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { selectedApp } = useDashboardStore();
  const deleteAgentMutation = useDeleteAgent(appId);

  // Get the namespace value for the query (undefined if 'all' or empty)
  const namespaceForQuery = namespace === 'all' || !namespace ? undefined : namespace;

  const { data: agents = [], isLoading: agentsLoading } = useGetAgents(appId, namespaceForQuery);
  const { data: namespaces = [] } = useGetNamespaces(appId);

  const filteredAgents = agents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      agent.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateAgent = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    setCreateDialogOpen(false);
  };

  const handleAgentClick = (agentId: string) => {
    navigate(`/apps/${appId}/agents/${agentId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, agent: AgentListItem) => {
    e.stopPropagation(); // Prevent triggering the click handler for the card
    setDeleteItem(agent);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteItem) return;
    deleteAgentMutation.mutate(deleteItem.id, {
      onSuccess: () => {
        setDeleteItem(null);
      },
    });
  };

  const handleNamespaceChange = (value: string) => {
    setNamespace(value);
  };

  return (
    <div className="flex h-full w-full flex-col p-8">
      <Breadcrumb className="mb-4">
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
                onClick={() => navigate(`/apps/${appId}/agents`)}
                className="hover:text-foreground cursor-pointer"
              >
                Agents
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Agents</h1>
          <p className="mt-2 text-gray-600">Manage AI agents for {selectedApp?.app_name}</p>
        </div>
        <div className="flex items-center gap-4">
          <Input
            className="w-[180px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />

          <Select value={namespace} onValueChange={handleNamespaceChange}>
            <SelectTrigger className="w-48 cursor-pointer">
              <SelectValue placeholder="Select namespace" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem className="cursor-pointer" value="all">
                All Namespaces
              </SelectItem>
              {namespaces.map((ns) => (
                <SelectItem className="cursor-pointer" key={ns.name} value={ns.name}>
                  {ns.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={handleCreateAgent}>Create Agent</Button>
        </div>
      </div>
      <div className="grid gap-6 overflow-y-auto py-2 sm:grid-cols-2 lg:grid-cols-3">
        {agentsLoading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} metadataCount={2} />
            ))}
          </>
        ) : filteredAgents.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No agents found"
              description="Get started by creating your first agent"
              actionText="Create Agent"
              onActionClick={handleCreateAgent}
            />
          </div>
        ) : (
          <>
            {filteredAgents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} onClick={handleAgentClick} onDeleteClick={handleDeleteClick} />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Agent"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteItem(null)}
        loading={deleteAgentMutation.isPending}
      />

      {/* Create Agent Dialog */}
      {appId && (
        <CreateAgentDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
          namespaces={namespaces}
        />
      )}
    </div>
  );
};

export default AgentManagement;
