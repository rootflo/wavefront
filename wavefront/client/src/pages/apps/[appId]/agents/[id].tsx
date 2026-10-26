import floConsoleService from '@app/api';
import ChatBot from '@app/components/ChatBot';
import PageTitle from '@app/components/PageTitle';
import StreamToggle from '@app/components/StreamToggle';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import VersionsDialog from '@app/components/VersionsDialog';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { ArrowLeft, MoreVertical } from 'lucide-react';
import { useDeleteAgent, usePromoteAgentVersion, useDeleteAgentVersion, useUpdateAgent } from '@app/hooks';
import { useGetAgent, useGetAgentVersions, useGetLLMConfigs, useGetTools } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { AgentStreamEvent } from '@app/types/agent';
import { ChatMessage, ChatMessageContent } from '@app/types/chat-message';
import { scrollToBottom } from '@app/utils/scroll';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import EditAgentDialog from './EditAgentDialog';
import { selectedToolsEqual, selectedToolsFromYaml } from './agent-tools';
import { formatAppName } from '@app/utils/string-formatting';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useChatAttachments } from '@app/hooks/use-chat-attachments';

const AgentDetail: React.FC = () => {
  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const navigate = useNavigate();
  const { notifyError } = useNotifyStore();
  const updateAgent = useUpdateAgent(appId);

  const [showUploadMenu, setShowUploadMenu] = useState(false);
  // Images and documents attached to the next message
  const {
    images: uploadedImages,
    documents: uploadedDocuments,
    uploadingImage,
    uploadingDocument,
    addImages: handleImageUpload,
    addDocuments: handleDocumentUpload,
    removeImage: handleRemoveImage,
    removeDocument: handleRemoveDocument,
    clear: clearAttachments,
  } = useChatAttachments({ onAdded: () => setShowUploadMenu(false) });
  const [showVariablesInput, setShowVariablesInput] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [versionsDialogOpen, setVersionsDialogOpen] = useState(false);
  // undefined = current_version
  const [selectedVersion, setSelectedVersion] = useState<number | undefined>(undefined);
  const [deleteItem, setDeleteItem] = useState<{
    id: string;
    name: string;
  } | null>(null);

  // Inference state
  const [inferenceInput, setInferenceInput] = useState('');
  const [inferenceVariables, setInferenceVariables] = useState('{}');
  const [runningInference, setRunningInference] = useState(false);

  // LLM Config selection state
  const [selectedLLMConfigId, setSelectedLLMConfigId] = useState<string>('');

  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);

  // Streaming state
  const [listenEventsEnabled, setListenEventsEnabled] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingEvents, setStreamingEvents] = useState<AgentStreamEvent[]>([]);
  const eventsContainerRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Datasource and tool selection state
  const [selectedTools, setSelectedTools] = useState<{ id: string; value: string }[]>([]);
  // True until selectedTools has been rebuilt from the loaded agent YAML.
  const pendingToolsHydrationRef = useRef(true);

  // Fetch data using hooks
  const { data: agent, isLoading: agentLoading } = useGetAgent(appId, id, selectedVersion);
  const { data: agentVersions = [], isLoading: versionsLoading } = useGetAgentVersions(appId, id);
  const { data: llmConfigs = [], isLoading: loadingConfigs } = useGetLLMConfigs(appId);
  const { data: availableTools = [] } = useGetTools(appId);
  const deleteAgentMutation = useDeleteAgent(appId);
  const promoteVersionMutation = usePromoteAgentVersion(appId, id);
  const deleteVersionMutation = useDeleteAgentVersion(appId, id);

  // Version currently shown (falls back to the agent's current_version).
  const displayVersion = selectedVersion ?? agent?.current_version;

  // Memoize toolsDetails to prevent unnecessary recreations
  const toolsDetails = useMemo(() => {
    return availableTools.map((tool) => {
      // finding the prefill value of the tool
      const prefillValues = tool.prefill_parameter_names || [];
      // fetching the prefill value from prefilled_value
      const prefilledValue = prefillValues.map((key) => {
        const value = tool.prefilled_value?.[key];

        return {
          [key]: value !== undefined ? value : `<${key}>`,
        };
      });

      return {
        name: tool.name,
        prefilled_values: prefilledValue,
        display_name: `${tool.resource_name ? tool.resource_name + ' - ' : ''}${tool.name}`,
        description: tool.description,
      };
    });
  }, [availableTools]);

  // Load YAML when the agent (or selected version) changes. Selection is
  // hydrated in a follow-up effect once tool details are available.
  useEffect(() => {
    if (!agent?.yaml_content) return;

    pendingToolsHydrationRef.current = true;
    setYamlContent(agent.yaml_content);
  }, [agent]);

  // Restore combobox selection from agent.tools. toolsDetails often arrives
  // after the agent payload; selection is hydrated once both are available.
  useEffect(() => {
    if (!pendingToolsHydrationRef.current || !yamlContent || toolsDetails.length === 0) {
      return;
    }

    const hydrated = selectedToolsFromYaml(yamlContent, toolsDetails);
    pendingToolsHydrationRef.current = false;
    setSelectedTools((prev) => (selectedToolsEqual(prev, hydrated) ? prev : hydrated));
  }, [yamlContent, toolsDetails]);

  const handleQuestionEntered = () => {
    if (inferenceInput.trim().length > 0) {
      handleRunInference();
      setInferenceInput('');
      requestAnimationFrame(() => {
        setTimeout(() => scrollToBottom('message-container', 'smooth'), 150);
      });
    }
  };

  const handleSave = async (yamlContent: string, options: { createNewVersion: boolean }) => {
    if (!appId || !id || !agent) return;

    // Rethrows so the editor keeps the unsaved YAML; useUpdateAgent has already shown the error
    await updateAgent.mutateAsync({
      agentId: id,
      yamlContent,
      version: displayVersion,
      createNewVersion: options.createNewVersion,
    });
  };

  const handlePromoteVersion = (version: number) => {
    promoteVersionMutation.mutate({ agentId: id!, version });
  };

  const handleDeleteVersion = (version: number) => {
    // If we're viewing the version being deleted, fall back to current_version so
    // the page doesn't try to refetch a now-deleted version.
    if (version === selectedVersion) {
      setSelectedVersion(undefined);
    }
    deleteVersionMutation.mutate({ agentId: id!, version });
  };

  const handleViewVersion = (version: number) => {
    setSelectedVersion(version);
    setVersionsDialogOpen(false);
  };

  const handleDeleteClick = () => {
    if (agent) {
      setDeleteItem({ id: agent.id, name: agent.name });
    }
  };

  const handleDeleteConfirm = () => {
    if (!deleteItem) return;
    deleteAgentMutation.mutate(deleteItem.id, {
      onSuccess: () => {
        setDeleteItem(null);
        navigate(`/apps/${appId}/agents`);
      },
    });
  };

  const handleRunInference = async () => {
    // Validate input: require either text input, uploaded image, uploaded document(s), or selected tools
    if (
      !appId ||
      !id ||
      (!inferenceInput.trim() &&
        uploadedImages.length === 0 &&
        uploadedDocuments.length === 0 &&
        selectedTools.length === 0)
    ) {
      notifyError('Please provide text input, upload an image/document, or select tools to run inference');
      return;
    }

    setRunningInference(true);
    try {
      let variables: Record<string, unknown> = {};
      if (inferenceVariables.trim()) {
        try {
          variables = JSON.parse(inferenceVariables);
        } catch {
          notifyError('Invalid JSON in variables field');
          setRunningInference(false);
          return;
        }
      }

      // Prepare inputs based on what's provided
      let inputs: string | Array<{ role: string; content: ChatMessageContent }>;
      const finalTextInput = inferenceInput.trim();
      // Handle different input combinations
      const conversationInputs: Array<{ role: string; content: ChatMessageContent }> = [];

      // Add previous chat history
      chatHistory.forEach((message) => {
        conversationInputs.push({
          role: message.role,
          content: message.content,
        });
      });

      // Add all images first if uploaded (wrapped with role/content)
      if (uploadedImages.length > 0) {
        uploadedImages.forEach((image) => {
          const imageMessage = {
            image_base64: image.base64Content,
            mime_type: image.mimeType,
            file_name: image.file.name,
          };
          setChatHistory((prev) => [...prev, { role: 'user', content: imageMessage }]);
          conversationInputs.push({
            role: 'user',
            content: imageMessage,
          });
        });
      }

      // Add all documents if uploaded (wrapped with role/content)
      if (uploadedDocuments.length > 0) {
        uploadedDocuments.forEach((doc) => {
          const documentMessage = {
            document_type: doc.documentType,
            document_base64: doc.base64Content,
            mime_type: doc.mimeType,
            file_name: doc.file.name,
            metadata: {
              filename: doc.file.name,
              size: doc.file.size,
            },
          };
          setChatHistory((prev) => [...prev, { role: 'user', content: documentMessage }]);
          conversationInputs.push({
            role: 'user',
            content: documentMessage,
          });
        });
      }

      // Add text input last if provided
      if (finalTextInput) {
        setChatHistory((prev) => [...prev, { role: 'user', content: finalTextInput }]);
        conversationInputs.push({
          role: 'user',
          content: finalTextInput,
        });
      }

      // Determine final inputs format
      if (conversationInputs.length > 0) {
        inputs = conversationInputs;
      } else {
        // Tools only - provide a generic instruction
        inputs = [
          {
            role: 'user',
            content: 'Please use the available tools to assist with the request.',
          },
        ];
      }
      if (listenEventsEnabled) {
        await handleStreamingInference(inputs, variables);
      } else {
        const result = await floConsoleService.agentService.runInference(
          id,
          inputs,
          variables,
          selectedLLMConfigId || undefined,
          selectedTools.length > 0 ? selectedTools.map((tool) => tool.value) : undefined,
          selectedVersion
        );
        const responseData = (result as { data?: { data?: { data?: { result?: string | object } } } }).data?.data?.data;
        const agentResponse =
          typeof responseData?.result === 'string'
            ? responseData.result
            : JSON.stringify(responseData?.result, null, 2);
        setChatHistory((prev) => [...prev, { role: 'assistant', content: agentResponse }]);
      }
      // Wait for DOM to update before scrolling
      requestAnimationFrame(() => {
        setTimeout(() => scrollToBottom('message-container', 'smooth'), 150);
      });
      clearAttachments();
    } catch (error) {
      console.error('Error running inference:', error);
    } finally {
      setRunningInference(false);
    }
  };

  /**
   * Run the agent as an SSE stream.
   *
   * Deltas land in a placeholder assistant bubble as they arrive; the lifecycle
   * and tool events go to the events panel. `output` overwrites the bubble
   * rather than appending: an agent with tools produces no deltas at all - see
   * the server's StreamingTapLLM - so for those the final event is the whole
   * reply.
   */
  const handleStreamingInference = async (inputs: string | unknown[], variables: Record<string, unknown>) => {
    if (!id) return;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setStreamingEvents([]);
    setIsStreaming(true);

    // The bubble the deltas accumulate into. Added up front so there is
    // somewhere to put the first token without a re-render race.
    setChatHistory((prev) => [...prev, { role: 'assistant', content: '' }]);

    const replaceLastAssistantMessage = (update: (current: string) => string) => {
      setChatHistory((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (!last || last.role !== 'assistant') return prev;
        next[next.length - 1] = {
          ...last,
          content: update(typeof last.content === 'string' ? last.content : ''),
        };
        return next;
      });
    };

    try {
      await floConsoleService.agentService.streamInference(id, inputs, variables, {
        llmInferenceConfigId: selectedLLMConfigId || undefined,
        toolNames: selectedTools.length > 0 ? selectedTools.map((tool) => tool.value) : undefined,
        version: selectedVersion,
        signal: controller.signal,
        onEvent: (event) => {
          switch (event.event_type) {
            case 'content_delta':
              replaceLastAssistantMessage((current) => current + (event.content ?? ''));
              break;

            // A guardrail withdrew text already on screen. `content` is the
            // whole of what may now be shown, not a delta, so it overwrites
            // rather than appends. Recorded in the event list too: a silent
            // rewrite of the bubble is indistinguishable from the model
            // having said the corrected thing all along.
            case 'retract':
              replaceLastAssistantMessage(() => event.content ?? '');
              setStreamingEvents((prev) => [...prev, event]);
              break;

            case 'output': {
              const result =
                typeof event.result === 'string' ? event.result : JSON.stringify(event.result ?? '', null, 2);
              replaceLastAssistantMessage(() => result);
              setStreamingEvents((prev) => [...prev, event]);
              break;
            }

            case 'error':
              notifyError(event.error || 'Agent inference failed');
              setStreamingEvents((prev) => [...prev, event]);
              break;

            default:
              setStreamingEvents((prev) => [...prev, event]);
          }

          const container = eventsContainerRef.current;
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        },
      });
    } catch (error) {
      // An abort is the user starting another run or leaving the page, not a
      // failure worth reporting.
      if ((error as Error)?.name !== 'AbortError' && abortControllerRef.current === controller) {
        notifyError(error instanceof Error ? error.message : 'Agent streaming failed');
      }
    } finally {
      if (abortControllerRef.current === controller) {
        setChatHistory((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'assistant' && last.content === '') {
            return prev.slice(0, -1);
          }
          return prev;
        });
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    }
  };

  // Leaving the page mid-run should stop the run, not leave a stream reading
  // into an unmounted component.
  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent p-3 sm:p-8">
      <PageBreadcrumb
        items={[
          { label: 'Agents', to: `/apps/${appId}/agents` },
          { label: agent?.name, loading: agentLoading },
        ]}
      />

      {agentLoading ? (
        <>
          <div className="flex min-w-0 items-center gap-2 pb-3 md:pb-6">
            <button
              type="button"
              aria-label="Back to agents"
              onClick={() => navigate(`/apps/${appId}/agents`)}
              className="frost-text hover:bg-frost-glass -ml-1 flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full md:hidden"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <PageTitle loading />
          </div>
          <div className="frost-text-muted flex items-center justify-center p-8">Loading agent...</div>
        </>
      ) : !agent ? (
        <div className="flex items-center justify-center p-8 text-red-600 dark:text-red-400">Agent not found</div>
      ) : (
        <>
          <div className="flex w-full shrink-0 flex-col gap-3 pb-3 md:flex-row md:items-center md:justify-between md:pb-6">
            <div className="flex min-w-0 items-center gap-2">
              <button
                type="button"
                aria-label="Back to agents"
                onClick={() => navigate(`/apps/${appId}/agents`)}
                className="frost-text hover:bg-frost-glass -ml-1 flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full md:hidden"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>
              <div className="min-w-0 flex-1">
                <PageTitle>{formatAppName(agent.name)}</PageTitle>
                {agent.current_version !== undefined && (
                  <p className="frost-text-muted text-xs md:hidden">Current: v{agent.current_version}</p>
                )}
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="Agent actions"
                    className="frost-text hover:bg-frost-glass flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full md:hidden"
                  >
                    <MoreVertical className="h-5 w-5" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => setVersionsDialogOpen(true)}>Versions</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setEditDialogOpen(true)}>Edit</DropdownMenuItem>
                  <DropdownMenuItem
                    className="text-red-600 focus:text-red-600 dark:text-red-400"
                    onClick={handleDeleteClick}
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <div className="flex flex-wrap items-center gap-2 md:gap-4">
              <StreamToggle enabled={listenEventsEnabled} onChange={setListenEventsEnabled} subject="reply" />
              {agentVersions.length > 0 && (
                <Select
                  value={displayVersion !== undefined ? String(displayVersion) : ''}
                  onValueChange={(val) => setSelectedVersion(Number(val))}
                >
                  <SelectTrigger className="min-w-0 flex-1 md:w-[150px] md:flex-none">
                    <SelectValue placeholder="Version" />
                  </SelectTrigger>
                  <SelectContent>
                    {[...agentVersions]
                      .sort((a, b) => a.version - b.version)
                      .map((v) => (
                        <SelectItem key={v.id} value={String(v.version)}>
                          v{v.version}
                          {v.is_current ? ' (current)' : ''}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              )}
              {agent.current_version !== undefined && (
                <Badge variant="secondary" className="hidden md:inline-flex">
                  Current: v{agent.current_version}
                </Badge>
              )}
              <Button variant="outline" className="hidden md:inline-flex" onClick={() => setVersionsDialogOpen(true)}>
                Versions
              </Button>
              <Button variant="outline" className="hidden md:inline-flex" onClick={() => setEditDialogOpen(true)}>
                Edit
              </Button>
              <Button variant="destructive" className="hidden md:inline-flex" onClick={handleDeleteClick}>
                Delete
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1">
            <ChatBot
              chatHistory={chatHistory}
              runningInference={runningInference}
              selectedLLMConfigId={selectedLLMConfigId}
              setSelectedLLMConfigId={setSelectedLLMConfigId}
              loadingConfigs={loadingConfigs}
              llmConfigs={llmConfigs}
              uploadedImages={uploadedImages}
              uploadedDocuments={uploadedDocuments}
              handleRemoveImage={handleRemoveImage}
              handleRemoveDocument={handleRemoveDocument}
              showUploadMenu={showUploadMenu}
              setShowUploadMenu={setShowUploadMenu}
              inferenceInput={inferenceInput}
              setInferenceInput={setInferenceInput}
              inferenceVariables={inferenceVariables}
              setInferenceVariables={setInferenceVariables}
              showVariablesInput={showVariablesInput}
              setShowVariablesInput={setShowVariablesInput}
              handleQuestionEntered={handleQuestionEntered}
              handleImageUpload={handleImageUpload}
              handleDocumentUpload={handleDocumentUpload}
              uploadingImage={uploadingImage}
              uploadingDocument={uploadingDocument}
              streamingEvents={streamingEvents}
              isStreaming={isStreaming}
              eventsContainerRef={eventsContainerRef}
            />
          </div>

          {/* Edit Agent Dialog */}
          <EditAgentDialog
            isOpen={editDialogOpen}
            onOpenChange={setEditDialogOpen}
            appId={appId!}
            yamlContent={yamlContent}
            selectedTools={selectedTools}
            toolsDetails={toolsDetails}
            editingVersion={displayVersion}
            onSave={async (updatedYamlContent, updatedSelectedTools, options) => {
              // Only adopt the new content once the server accepted it; a rejection keeps the dialog open.
              await handleSave(updatedYamlContent, options);
              setYamlContent(updatedYamlContent);
              setSelectedTools(updatedSelectedTools);
            }}
            saving={updateAgent.isPending}
          />

          {/* Versions Dialog */}
          <VersionsDialog
            isOpen={versionsDialogOpen}
            onOpenChange={setVersionsDialogOpen}
            entityLabel="agent"
            versions={agentVersions}
            loading={versionsLoading}
            selectedVersion={displayVersion}
            onView={handleViewVersion}
            onPromote={handlePromoteVersion}
            onDelete={handleDeleteVersion}
            actionPending={promoteVersionMutation.isPending || deleteVersionMutation.isPending}
          />

          {/* Delete Confirmation Dialog */}
          <DeleteConfirmationDialog
            isOpen={!!deleteItem}
            title="Delete Agent"
            message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
            onConfirm={handleDeleteConfirm}
            onCancel={() => setDeleteItem(null)}
            loading={deleteAgentMutation.isPending}
          />
        </>
      )}
    </div>
  );
};

export default AgentDetail;
