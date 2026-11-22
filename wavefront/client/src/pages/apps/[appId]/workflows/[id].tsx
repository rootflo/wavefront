import floConsoleService from '@app/api';
import MobileBackButton from '@app/components/MobileBackButton';
import ChatBot from '@app/components/ChatBot';
import PageTitle from '@app/components/PageTitle';
import StreamToggle from '@app/components/StreamToggle';
import VersionsDialog from '@app/components/VersionsDialog';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import { appEnv } from '@app/config/env';
import { useGetWorkflowVersions, usePromoteWorkflowVersion, useDeleteWorkflowVersion } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { ChatMessage, ChatMessageContent } from '@app/types/chat-message';
import { WorkflowEvent } from '@app/types/workflow';
import { scrollToBottom } from '@app/utils/scroll';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useParams } from 'react-router';
import { formatAppName } from '@app/utils/string-formatting';
import { useWorkflowUpdatedListener } from './useWorkflowDraftSave';
import { useChatAttachments } from '@app/hooks/use-chat-attachments';
import { useGetWorkflow } from '@app/hooks';

type MessageInput = { role: 'user' | 'assistant'; content: ChatMessageContent };

const WorkflowDetail: React.FC = () => {
  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const { notifyError } = useNotifyStore();
  // Saved YAML shown on the page; editing happens in the standalone editor tab
  const [versionsDialogOpen, setVersionsDialogOpen] = useState(false);
  // undefined = current_version
  const [selectedVersion, setSelectedVersion] = useState<number | undefined>(undefined);
  const {
    data: workflow = null,
    isLoading: workflowLoading,
    refetch: refetchWorkflow,
  } = useGetWorkflow(appId, id, selectedVersion);

  const { data: workflowVersions = [], isLoading: versionsLoading } = useGetWorkflowVersions(appId, id);
  const promoteVersionMutation = usePromoteWorkflowVersion(appId, id);
  const deleteVersionMutation = useDeleteWorkflowVersion(appId, id);

  // Version currently shown (falls back to the workflow's current_version).
  const displayVersion = selectedVersion ?? workflow?.current_version;

  // Inference state
  const [inferenceInput, setInferenceInput] = useState('');
  const [inferenceVariables, setInferenceVariables] = useState('{}');
  const [runningInference, setRunningInference] = useState(false);

  // Chat history and menu states
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
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
  // The single-image request field takes the first attached image
  const uploadedImage = uploadedImages[0] ?? null;
  const [showVariablesInput, setShowVariablesInput] = useState(false);
  const [selectedLLMConfigId, setSelectedLLMConfigId] = useState<string>('');

  // Document upload state
  const [outputJsonEnabled, setOutputJsonEnabled] = useState(false);

  // SSE state
  const [listenEventsEnabled, setListenEventsEnabled] = useState<boolean>(false);
  const [streamingEvents, setStreamingEvents] = useState<WorkflowEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);

  // Ref for auto-scrolling events container
  const eventsContainerRef = useRef<HTMLDivElement>(null);
  // Ref for current abort controller - used so unmount cleanup doesn't depend on state
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup SSE request only on unmount (avoid aborting when abortController state changes)
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

  // Reload when this workflow is created or saved from an editor tab
  useWorkflowUpdatedListener(
    useCallback(
      (updatedId: string) => {
        if (updatedId === id) void refetchWorkflow();
      },
      [id, refetchWorkflow]
    )
  );

  const handleOpenEditor = () => {
    const versionQuery = selectedVersion !== undefined ? `?version=${selectedVersion}` : '';
    window.open(`/apps/${appId}/workflows/${id}/editor${versionQuery}`, '_blank', 'noopener');
  };

  const handlePromoteVersion = (version: number) => {
    promoteVersionMutation.mutate({ workflowId: id!, version });
  };

  const handleDeleteVersion = (version: number) => {
    // If we're viewing the version being deleted, fall back to current_version so
    // the page doesn't keep showing / refetch a now-deleted version.
    const wasViewingDeleted = version === selectedVersion;
    if (wasViewingDeleted) {
      setSelectedVersion(undefined);
    }
    deleteVersionMutation.mutate({ workflowId: id!, version });
  };

  const handleViewVersion = (version: number) => {
    setSelectedVersion(version);
    setVersionsDialogOpen(false);
  };

  const handleQuertionEntered = () => {
    if (inferenceInput.trim().length > 0 || uploadedImages.length > 0 || uploadedDocuments.length > 0) {
      handleRunInference();
      setInferenceInput('');
      clearAttachments();
      requestAnimationFrame(() => {
        setTimeout(() => scrollToBottom('message-container', 'smooth'), 150);
      });
    }
  };
  const handleRunInference = async () => {
    // Validate input: require either text input, uploaded image, or uploaded document(s)
    if (!id || (!inferenceInput.trim() && !uploadedImage && uploadedDocuments.length === 0)) {
      notifyError('Please provide text input, upload an image/document');
      return;
    }

    setRunningInference(true);

    // Abort any existing fetchEventSource
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // Clear previous results
    setStreamingEvents([]);

    try {
      let variables = {};
      if (inferenceVariables.trim()) {
        try {
          variables = JSON.parse(inferenceVariables);
        } catch {
          notifyError('Invalid JSON in variables field');
          setRunningInference(false);
          return;
        }
      }

      let inputs: string | MessageInput[];

      // Handle different input combinations
      const messageInputs: MessageInput[] = [];
      chatHistory.forEach((message) => {
        messageInputs.push({
          role: message.role,
          content: message.content,
        });
      });

      // Add all images if uploaded (using uploadedImages array)
      if (uploadedImages.length > 0) {
        uploadedImages.forEach((image) => {
          const imageMessage = {
            image_base64: image.base64Content,
            mime_type: image.mimeType,
            file_name: image.file.name,
          };
          messageInputs.push({ role: 'user', content: imageMessage });
          setChatHistory((prev) => [...prev, { role: 'user', content: imageMessage }]);
        });
      } else if (uploadedImage) {
        // Fallback to single image for backward compatibility
        const imageBase64Content = uploadedImage.base64.split(',')[1];
        const imageMessage = {
          image_base64: imageBase64Content,
          mime_type: uploadedImage.mimeType,
          file_name: uploadedImage.file?.name,
        };
        messageInputs.push({ role: 'user', content: imageMessage });
        setChatHistory((prev) => [...prev, { role: 'user', content: imageMessage }]);
      }

      // Add all documents if uploaded
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
          messageInputs.push({ role: 'user', content: documentMessage });
          setChatHistory((prev) => [...prev, { role: 'user', content: documentMessage }]);
        });
      }

      // Add text input if provided
      if (inferenceInput.trim()) {
        const textInput = inferenceInput.trim();
        messageInputs.push({ role: 'user', content: textInput });
        setChatHistory((prev) => [...prev, { role: 'user', content: textInput }]);
      }

      // Determine final inputs format
      if (messageInputs.length > 0) {
        inputs = messageInputs;
      } else {
        // This shouldn't happen due to validation, but fallback
        inputs = '';
      }

      if (listenEventsEnabled) {
        // Handle SSE inference
        await handleSSEInference(inputs, variables);
      } else {
        // Handle normal inference
        const result = await floConsoleService.workflowService.runInference(
          id,
          inputs,
          variables,
          outputJsonEnabled,
          selectedVersion
        );
        const resultContent = result.data?.data?.data?.result;
        if (resultContent) {
          setChatHistory((prev) => [...prev, { role: 'assistant', content: resultContent }]);
        }
      }
    } catch (error) {
      console.error('Error running inference:', error);
    } finally {
      if (!listenEventsEnabled) {
        setRunningInference(false);
      }
    }
  };

  const handleSSEInference = async (
    inputs: string | Array<{ role: 'user' | 'assistant'; content: ChatMessageContent }>,
    variables: Record<string, unknown>
  ) => {
    if (!id) return;

    try {
      setIsStreaming(true);
      setStreamingEvents([]); // Clear previous events immediately

      const token = localStorage.getItem('authToken');
      if (!token) {
        throw new Error('Authentication token not found');
      }

      const baseUrl = appEnv.baseURL;

      // Prepare request body
      const requestBody = {
        inputs,
        variables,
        listen_events: true,
        output_json_enabled: outputJsonEnabled,
      };

      const url =
        selectedVersion !== undefined
          ? `${baseUrl}/v1/${appId}/floware/v2/workflows/${id}/inference?version=${selectedVersion}`
          : `${baseUrl}/v1/${appId}/floware/v2/workflows/${id}/inference`;

      // Create abort controller for cleanup
      const controller = new AbortController();
      abortControllerRef.current = controller;

      // RAW FETCH with immediate ReadableStream processing
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
          // 'Accept-Encoding': 'gzip,deflate,br',
        },
        mode: 'cors',
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Authentication failed. Please login again.');
        } else if (response.status === 403) {
          throw new Error('Access denied. Check your permissions.');
        } else if (response.status === 404) {
          throw new Error('Workflow not found.');
        } else if (response.status >= 500) {
          throw new Error('Server error. Please try again later.');
        } else {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
      }

      const reader = response.body?.pipeThrough(new TextDecoderStream()).getReader();
      // const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('ReadableStream not supported');
      }

      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          // IMMEDIATE chunk processing - no delays
          // const chunk = decoder.decode(value, { stream: true });
          const chunk = value;
          buffer += chunk;

          // PROPER SSE EVENT PROCESSING - split on double newline
          const events = buffer.split('\n\n');
          buffer = events.pop() || ''; // Keep incomplete event in buffer

          // Process complete events
          for (let i = 0; i < events.length; i++) {
            const event = events[i];
            if (event.trim() === '') continue;

            // Parse SSE event format properly
            const lines = event.split('\n');
            let data = '';

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                data += line.substring(6) + '\n';
              }
            }

            // Process the complete event
            if (data.trim()) {
              try {
                const eventData = JSON.parse(data.trim());

                // Add timestamp if not present
                if (!eventData.timestamp) {
                  eventData.timestamp = Date.now() / 1000;
                }

                // IMMEDIATE state update with flushSync for critical updates
                flushSync(() => {
                  setStreamingEvents((prev) => {
                    const newEvents = [...prev, eventData];
                    return newEvents;
                  });
                });

                // IMMEDIATE scroll update
                if (eventsContainerRef.current) {
                  const container = eventsContainerRef.current;
                  const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;

                  if (isNearBottom) {
                    container.scrollTop = container.scrollHeight;
                  }
                }

                // Handle different event types
                switch (eventData.event_type) {
                  case 'workflow_started':
                    break;

                  case 'node_started':
                    break;

                  case 'node_completed':
                    break;

                  case 'node_failed':
                    console.error('Node failed:', eventData.node_name, eventData.error);
                    break;

                  case 'workflow_completed':
                    break;

                  case 'workflow_failed':
                    console.error('Workflow failed:', eventData.error);
                    break;

                  case 'output':
                    // Use flushSync for critical final update
                    flushSync(() => {
                      const agentResponse =
                        typeof eventData.result === 'string'
                          ? eventData.result
                          : JSON.stringify(eventData.result, null, 2);
                      setChatHistory((prev) => [
                        ...prev,
                        {
                          role: 'assistant',
                          content: agentResponse,
                        },
                      ]);
                    });

                    // IMMEDIATE connection close
                    reader.cancel();
                    cleanup();
                    return; // Exit the while loop

                  default:
                    break;
                }
              } catch (e) {
                console.error('Error parsing event data:', e, 'Raw event:', event);
              }
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          // Stream aborted by user
        } else {
          console.error('Stream error:', error);
          throw error;
        }
      } finally {
        reader.releaseLock();
        cleanup();
      }
    } catch (error) {
      console.error('Error setting up SSE connection:', error);

      if (error instanceof Error && error.name !== 'AbortError') {
        const errorMessage = error.message.includes('Authentication')
          ? 'Authentication failed. Please login again.'
          : `Failed to connect: ${error.message}`;

        notifyError(errorMessage);
      }

      cleanup();
    }

    // Cleanup helper function
    function cleanup() {
      setRunningInference(false);
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  return (
    <div className="h-full bg-transparent py-2">
      <div className="flex h-full w-full flex-col gap-4 md:gap-6">
        <div className="flex flex-wrap items-center justify-between gap-3 md:gap-4">
          <div className="flex min-w-0 items-center gap-2">
            <MobileBackButton to={`/apps/${appId}/workflows`} label="Back to workflows" />
            <PageTitle loading={!workflow && workflowLoading}>{formatAppName(workflow?.name)}</PageTitle>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 md:w-auto md:justify-end md:gap-4">
            <Label
              htmlFor="output-json-toggle"
              className="frost-control ring-frost-border flex h-9 cursor-pointer items-center gap-2 rounded-md px-3 ring-1"
            >
              <span className="frost-text text-[13px] font-medium">JSON output</span>
              <Switch id="output-json-toggle" checked={outputJsonEnabled} onCheckedChange={setOutputJsonEnabled} />
            </Label>
            <StreamToggle
              enabled={listenEventsEnabled}
              onChange={setListenEventsEnabled}
              subject="result"
              liveHint="Shows each step as it runs"
            />
            {workflowVersions.length > 0 && (
              <Select
                value={displayVersion !== undefined ? String(displayVersion) : ''}
                onValueChange={(val) => setSelectedVersion(Number(val))}
              >
                <SelectTrigger className="min-w-0 flex-1 md:w-[150px] md:flex-none">
                  <SelectValue placeholder="Version" />
                </SelectTrigger>
                <SelectContent>
                  {[...workflowVersions]
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
            {workflow?.current_version !== undefined && (
              <Badge variant="secondary">Current: v{workflow.current_version}</Badge>
            )}
            <Button variant="outline" onClick={() => setVersionsDialogOpen(true)}>
              Versions
            </Button>
            <Button variant="outline" onClick={handleOpenEditor} title="Opens the editor in a new tab">
              Edit
            </Button>
          </div>
        </div>

        <div className="min-h-0 w-full flex-1 pb-2">
          <div className="flex h-full min-h-[28rem] w-full flex-col">
            <div className="min-h-0 flex-1">
              <ChatBot
                chatHistory={chatHistory}
                runningInference={runningInference}
                selectedLLMConfigId={selectedLLMConfigId}
                setSelectedLLMConfigId={setSelectedLLMConfigId}
                loadingConfigs={false}
                llmConfigs={[]}
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
                handleQuestionEntered={handleQuertionEntered}
                handleImageUpload={handleImageUpload}
                handleDocumentUpload={handleDocumentUpload}
                uploadingImage={uploadingImage}
                uploadingDocument={uploadingDocument}
                isModelSwitchEnabled={false}
                emptyTitle="Run this workflow"
                emptyDescription="Enter an input below to run it and see the result of each step."
                inputPlaceholder="Enter input for the workflow"
                streamingEvents={streamingEvents}
                isStreaming={isStreaming}
                eventsContainerRef={eventsContainerRef}
              />
            </div>
          </div>
        </div>
      </div>

      <VersionsDialog
        isOpen={versionsDialogOpen}
        onOpenChange={setVersionsDialogOpen}
        entityLabel="workflow"
        versions={workflowVersions}
        loading={versionsLoading}
        selectedVersion={displayVersion}
        onView={handleViewVersion}
        onPromote={handlePromoteVersion}
        onDelete={handleDeleteVersion}
        actionPending={promoteVersionMutation.isPending || deleteVersionMutation.isPending}
      />
    </div>
  );
};

export default WorkflowDetail;
