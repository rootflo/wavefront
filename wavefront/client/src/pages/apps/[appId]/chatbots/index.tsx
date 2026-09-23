import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
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
import { Switch } from '@app/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetChatbots, useGetLLMConfigs, useGetNamespaces } from '@app/hooks';
import { getChatbotsKey } from '@app/hooks/data/query-keys';
import { copyToClipboard, extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { Chatbot } from '@app/types/chatbot';
import { useQueryClient } from '@tanstack/react-query';
import { Copy, Pencil, Trash2 } from 'lucide-react';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import CreateChatbotDialog from './CreateChatbotDialog';
import EditChatbotDialog from './EditChatbotDialog';
import { formatTemperature } from './schemas';

const ChatbotsPage: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [namespace, setNamespace] = useState('all');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<Chatbot | null>(null);
  const [deleteItem, setDeleteItem] = useState<Chatbot | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Per-row so two toggles cannot interleave and leave the UI disagreeing
  // with the server about which chatbot is live.
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const namespaceForQuery = namespace === 'all' || !namespace ? undefined : namespace;

  const { data: chatbots = [], isLoading } = useGetChatbots(app, namespaceForQuery);
  const { data: namespaces = [] } = useGetNamespaces(app);
  const { data: llmConfigs = [] } = useGetLLMConfigs(app);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getChatbotsKey(app || '', namespaceForQuery) });
  };

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

  const handleToggleEnabled = async (chatbot: Chatbot, enabled: boolean) => {
    setTogglingId(chatbot.id);
    try {
      await floConsoleService.chatbotService.updateChatbot(chatbot.id, { enabled });
      notifySuccess(enabled ? 'Chatbot enabled' : 'Chatbot disabled');
      invalidate();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to update chatbot');
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.chatbotService.deleteChatbot(deleteItem.id);
      notifySuccess('Chatbot deleted successfully');
      invalidate();
      setDeleteItem(null);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to delete chatbot');
    } finally {
      setDeleting(false);
    }
  };

  const handleCreateSuccess = () => {
    invalidate();
    setCreateDialogOpen(false);
  };

  const handleEditSuccess = () => {
    invalidate();
    setEditItem(null);
  };

  const filteredChatbots = chatbots.filter((chatbot) => {
    const query = searchQuery.toLowerCase();
    return (
      chatbot.name.toLowerCase().includes(query) ||
      chatbot.namespace.toLowerCase().includes(query) ||
      (chatbot.description && chatbot.description.toLowerCase().includes(query))
    );
  });

  return (
    // p-8 and the breadcrumb come from the page itself: the voice-agents pages
    // this table was modelled on get theirs from VoiceAgentsLayout, which a
    // top-level route like this one does not have.
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
                onClick={() => navigate(`/apps/${app}/chatbots`)}
                className="hover:text-foreground cursor-pointer"
              >
                Chatbots
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="min-w-0">
        <div className="mb-8 flex w-full items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Chatbots</h1>
            <p className="mt-2 text-gray-600">Manage chatbots for {selectedApp?.app_name}</p>
          </div>
          <div className="flex shrink-0 items-center gap-4">
            <Input
              type="text"
              placeholder="Search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-[180px]"
            />

            <Select value={namespace} onValueChange={setNamespace}>
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

            <Button onClick={() => setCreateDialogOpen(true)}>
              <p className="text-sm">Create Chatbot</p>
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-10">
            <div className="text-gray-500">Loading chatbots...</div>
          </div>
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
          // Nine columns including a full uuid: let the table scroll inside its
          // own box rather than pushing the page sideways on a narrow window.
          <div className="overflow-x-auto rounded-md border">
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
                        <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(chatbot.id)}>
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-600">{chatbot.namespace}</span>
                    </TableCell>
                    <TableCell className="max-w-xs truncate">{chatbot.description || '-'}</TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-600">{describeModel(chatbot.llm_config_id)}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-600">{formatTemperature(chatbot.config)}</span>
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Switch
                        checked={chatbot.enabled}
                        disabled={togglingId === chatbot.id}
                        onCheckedChange={(checked) => handleToggleEnabled(chatbot, checked)}
                      />
                    </TableCell>
                    <TableCell>{new Date(chatbot.created_at).toLocaleDateString()}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setEditItem(chatbot)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setDeleteItem(chatbot)} title="Delete">
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
          title="Delete Chatbot"
          message={`Are you sure you want to delete "${deleteItem?.name}"? Existing conversations stay readable but cannot accept new messages.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteItem(null)}
          loading={deleting}
        />

        {app && (
          <CreateChatbotDialog
            isOpen={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            appId={app}
            namespaces={namespaces}
            defaultNamespace={namespaceForQuery || 'default'}
            onSuccess={handleCreateSuccess}
          />
        )}

        {app && editItem && (
          <EditChatbotDialog
            isOpen={!!editItem}
            onOpenChange={(open) => !open && setEditItem(null)}
            appId={app}
            chatbot={editItem}
            namespaces={namespaces}
            onSuccess={handleEditSuccess}
          />
        )}
      </div>
    </div>
  );
};

export default ChatbotsPage;
