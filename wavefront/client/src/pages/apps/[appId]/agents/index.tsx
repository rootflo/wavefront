import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import AgentCard from '@app/components/AgentCard';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import ResourceList, { ListViewToggle } from '@app/components/ResourceList';
import { useListView } from '@app/lib/list-view';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useDeleteAgent, useGetAgents, useGetNamespaces } from '@app/hooks';
import { copyToClipboard, formatAppName } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { AgentListItem } from '@app/types/agent';
import dayjs from 'dayjs';
import { Copy, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateAgentDialog from './CreateAgentDialog';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const AgentManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const [view, setView] = useListView('agents');
  const { notifySuccess, notifyError } = useNotifyStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [namespace, setNamespace] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { selectedApp } = useDashboardStore();
  const deleteAgentMutation = useDeleteAgent(appId);
  const deletion = useDeleteConfirm<AgentListItem>((item) => deleteAgentMutation.mutateAsync(item.id));

  // Get the namespace value for the query (undefined if 'all' or empty)
  const namespaceForQuery = namespace === 'all' || !namespace ? undefined : namespace;

  const { data: agents = [], isLoading: agentsLoading } = useGetAgents(appId, namespaceForQuery);
  const { data: namespaces = [] } = useGetNamespaces(appId);

  const filteredAgents = agents.filter((agent) => matchesSearch(searchTerm, agent.name, agent.id));

  const handleCreateAgent = () => {
    setCreateDialogOpen(true);
  };

  const handleAgentClick = (agentId: string) => {
    navigate(`/apps/${appId}/agents/${agentId}`);
  };

  const handleCopyId = async (id: string) => {
    if (await copyToClipboard(id)) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const handleNamespaceChange = (value: string) => {
    setNamespace(value);
  };

  return (
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Agents', to: `/apps/${appId}/agents` }]} />

      <ListHeader
        title="Agents"
        count={filteredAgents.length || undefined}
        subtitle={<>Manage AI agents for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search agents' }}
        filters={
          <FilterSelect
            label="Namespace"
            value={namespace}
            onValueChange={handleNamespaceChange}
            allValue="all"
            options={[
              { value: 'all', label: 'All namespaces' },
              ...namespaces.map((ns) => ({ value: ns.name, label: ns.name })),
            ]}
          />
        }
        extras={<ListViewToggle view={view} onChange={setView} />}
        primary={{ label: 'Create agent', onClick: handleCreateAgent }}
      />
      {agentsLoading || filteredAgents.length === 0 ? (
        <div className="-mx-1 -mt-2 grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">
          {agentsLoading ? (
            Array.from({ length: 6 }).map((_, index) => <ResourceCardSkeleton key={index} metadataCount={2} />)
          ) : (
            <div className="col-span-full mt-10 flex justify-center">
              <EmptyStateCard
                title="No agents found"
                description="Get started by creating your first agent"
                actionText="Create Agent"
                onActionClick={handleCreateAgent}
              />
            </div>
          )}
        </div>
      ) : (
        <ResourceList
          view={view}
          cards={filteredAgents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onClick={handleAgentClick}
              onDeleteClick={(e, item) => deletion.ask(item, e)}
            />
          ))}
          table={
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Namespace</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAgents.map((agent) => (
                  <TableRow key={agent.id} className="cursor-pointer" onClick={() => handleAgentClick(agent.id)}>
                    <TableCell className="max-w-[220px] truncate font-medium" title={agent.name}>
                      {formatAppName(agent.name)}
                    </TableCell>
                    <TableCell className="max-w-[240px]" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <span className="truncate font-mono text-xs" title={agent.id}>
                          {agent.id}
                        </span>
                        <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(agent.id)}>
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="frost-text-muted">{agent.namespace || '—'}</TableCell>
                    <TableCell className="frost-text-muted">
                      {agent.current_version !== undefined ? `v${agent.current_version}` : '—'}
                    </TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      {agent.updated_at ? dayjs(agent.updated_at).format('DD MMM YYYY') : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" title="Delete" onClick={(e) => deletion.ask(agent, e)}>
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
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
        title="Delete Agent"
        message={`Are you sure you want to delete "${deletion.item?.name}"? This action cannot be undone.`}
      />

      {/* Create Agent Dialog */}
      {appId && (
        <CreateAgentDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          namespaces={namespaces}
        />
      )}
    </div>
  );
};

export default AgentManagement;
