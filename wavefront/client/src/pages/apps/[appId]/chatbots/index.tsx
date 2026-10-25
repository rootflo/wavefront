import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import ResourceCard from '@app/components/ResourceCard';
import ResourceList, { ListViewToggle, ResourceListSkeleton } from '@app/components/ResourceList';
import { useListView } from '@app/lib/list-view';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Switch } from '@app/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useDeleteChatbot, useGetChatbots, useGetLLMConfigs, useGetNamespaces, useSetChatbotEnabled } from '@app/hooks';
import { copyToClipboard } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { Chatbot } from '@app/types/chatbot';
import { Copy, Pencil, Trash2, MessageSquare, Power } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';

import ChatbotFormDialog from './ChatbotFormDialog';
import { formatTemperature } from './schemas';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/lib/search';

const ChatbotsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const [view, setView] = useListView('chatbots');
  const setChatbotEnabled = useSetChatbotEnabled(app);
  const deleteChatbot = useDeleteChatbot(app);
  const deletion = useDeleteConfirm<Chatbot>((item) => deleteChatbot.mutateAsync(item.id));
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [namespace, setNamespace] = useState('all');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<Chatbot | null>(null);
  // Per-row so two toggles cannot interleave and leave the UI disagreeing
  // with the server about which chatbot is live.

  const namespaceForQuery = namespace === 'all' || !namespace ? undefined : namespace;

  const { data: chatbots = [], isLoading } = useGetChatbots(app, namespaceForQuery);
  const { data: namespaces = [] } = useGetNamespaces(app);
  const { data: llmConfigs = [] } = useGetLLMConfigs(app);

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const describeModel = (llmConfigId: string) => {
    const config = llmConfigs.find((item) => item.id === llmConfigId);
    // A chatbot can outlive its LLM config; show the id rather than nothing.
    return config ? config.display_name : `${llmConfigId.slice(0, 8)}… (unavailable)`;
  };

  const handleToggleEnabled = (chatbot: Chatbot, enabled: boolean) => {
    setChatbotEnabled.mutate({ chatbotId: chatbot.id, enabled });
  };

  /** Disables just the row whose enabled switch is being saved. */
  const isToggling = (chatbotId: string) =>
    setChatbotEnabled.isPending && setChatbotEnabled.variables?.chatbotId === chatbotId;

  const filteredChatbots = chatbots.filter((chatbot) =>
    matchesSearch(searchQuery, chatbot.name, chatbot.namespace, chatbot.description)
  );

  return (
    // p-8 and the breadcrumb come from the page itself: the voice-agents pages
    // this table was modelled on get theirs from VoiceAgentsLayout, which a
    // top-level route like this one does not have.
    <div className="flex h-full w-full flex-col p-4 sm:p-8">
      <PageBreadcrumb items={[{ label: 'Chatbots', to: `/apps/${app}/chatbots` }]} />

      <div className="min-w-0">
        <ListHeader
          extras={<ListViewToggle view={view} onChange={setView} />}
          title="Chatbots"
          count={filteredChatbots.length || undefined}
          subtitle={<>Manage chatbots for {selectedApp?.app_name}</>}
          search={{ value: searchQuery, onChange: setSearchQuery, placeholder: 'Search chatbots' }}
          filters={
            <FilterSelect
              label="Namespace"
              value={namespace}
              onValueChange={setNamespace}
              allValue="all"
              options={[
                { value: 'all', label: 'All namespaces' },
                ...namespaces.map((ns) => ({ value: ns.name, label: ns.name })),
              ]}
            />
          }
          primary={{ label: 'Create chatbot', onClick: () => setCreateDialogOpen(true) }}
        />

        {isLoading ? (
          <ResourceListSkeleton view={view} />
        ) : filteredChatbots.length === 0 ? (
          <div className="mt-10 flex justify-center">
            <EmptyStateCard
              title="No chatbots found"
              description={
                searchQuery ? 'No chatbots match your search.' : 'Get started by creating your first chatbot'
              }
              actionText="Create Chatbot"
              onActionClick={() => setCreateDialogOpen(true)}
            />
          </div>
        ) : (
          <ResourceList
            view={view}
            cards={
              <>
                {filteredChatbots.map((chatbot) => (
                  <ResourceCard
                    key={chatbot.id}
                    icon={MessageSquare}
                    title={chatbot.name}
                    description={chatbot.description || undefined}
                    metadata={[
                      { label: 'Id', value: chatbot.id, isMono: true, isCopyable: true },
                      { label: 'Namespace', value: chatbot.namespace },
                      { label: 'Model', value: describeModel(chatbot.llm_config_id) },
                      { label: 'Temperature', value: `Temp ${formatTemperature(chatbot.config)}` },
                      {
                        label: 'Status',
                        value: chatbot.enabled ? 'Enabled' : 'Disabled',
                        className: chatbot.enabled
                          ? 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300'
                          : 'bg-frost-glass-strong frost-text-subtle',
                      },
                      { label: 'Created', value: new Date(chatbot.created_at).toLocaleDateString() },
                    ]}
                    onEditClick={() => setEditItem(chatbot)}
                    onDeleteClick={() => deletion.ask(chatbot)}
                    deleteTitle="Delete chatbot"
                    extraActions={[
                      {
                        label: chatbot.enabled ? 'Disable' : 'Enable',
                        icon: Power,
                        disabled: isToggling(chatbot.id),
                        onClick: () => handleToggleEnabled(chatbot, !chatbot.enabled),
                      },
                    ]}
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
                    <TableHead>Namespace</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Temperature</TableHead>
                    <TableHead>Enabled</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredChatbots.map((chatbot) => (
                    <TableRow key={chatbot.id}>
                      <TableCell className="font-medium">{chatbot.name}</TableCell>
                      <TableCell className="max-w-[260px]" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <span className="truncate font-mono text-xs" title={chatbot.id}>
                            {chatbot.id}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Copy ID"
                            onClick={() => void handleCopyId(chatbot.id)}
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="frost-text-muted text-sm">{chatbot.namespace}</span>
                      </TableCell>
                      <TableCell className="max-w-xs truncate">{chatbot.description || '-'}</TableCell>
                      <TableCell>
                        <span className="frost-text-muted text-sm">{describeModel(chatbot.llm_config_id)}</span>
                      </TableCell>
                      <TableCell>
                        <span className="frost-text-muted text-sm">{formatTemperature(chatbot.config)}</span>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Switch
                          checked={chatbot.enabled}
                          disabled={isToggling(chatbot.id)}
                          onCheckedChange={(checked) => handleToggleEnabled(chatbot, checked)}
                        />
                      </TableCell>
                      <TableCell>{new Date(chatbot.created_at).toLocaleDateString()}</TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-2">
                          <Button variant="ghost" size="sm" onClick={() => setEditItem(chatbot)} title="Edit">
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => deletion.ask(chatbot)} title="Delete">
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
          title="Delete Chatbot"
          message={`Are you sure you want to delete "${deletion.item?.name}"? Existing conversations stay readable but cannot accept new messages.`}
        />

        {app && (
          <ChatbotFormDialog
            isOpen={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            appId={app}
            namespaces={namespaces}
            defaultNamespace={namespaceForQuery || 'default'}
          />
        )}

        {app && editItem && (
          <ChatbotFormDialog
            isOpen={!!editItem}
            onOpenChange={(open) => !open && setEditItem(null)}
            appId={app}
            chatbot={editItem}
            namespaces={namespaces}
          />
        )}
      </div>
    </div>
  );
};

export default ChatbotsPage;
