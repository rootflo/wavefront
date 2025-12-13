import floConsoleService from '@app/api';
import ChatBot from '@app/components/ChatBot';
import { Button } from '@app/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { appEnv } from '@app/config/env';
import { useNotifyStore } from '@app/store';
import { Workflow, WorkflowEvent } from '@app/types/workflow';
import { scrollToBottom } from '@app/utils/scroll';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useParams } from 'react-router';

const WorkflowDetail: React.FC = () => {
  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [yamlContent, setYamlContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);

  // Inference state
  const [inferenceInput, setInferenceInput] = useState('');
  const [inferenceVariables, setInferenceVariables] = useState('{}');
  const [runningInference, setRunningInference] = useState(false);

  // Image upload state (keeping single for backward compatibility, but also adding array for ChatBot)
  const [uploadedImage, setUploadedImage] = useState<{
    file: File;
    base64: string;
    mimeType: string;
  } | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<
    Array<{
      file: File;
      base64: string;
      base64Content: string;
      mimeType: string;
    }>
  >([]);

  // Chat history and menu states
  const [chatHistory, setChatHistory] = useState<{ role: 'user' | 'assistant'; content: any }[]>([]);
  const [showUploadMenu, setShowUploadMenu] = useState(false);
  const [showVariablesInput, setShowVariablesInput] = useState(false);
  const [selectedLLMConfigId, setSelectedLLMConfigId] = useState<string>('');

  // Document upload state
  const [uploadedDocuments, setUploadedDocuments] = useState<
    Array<{
      file: File;
      base64: string; // Full data URL for display
      base64Content: string; // Just base64 content for API
      mimeType: string;
      documentType: 'pdf' | 'txt';
    }>
  >([]);
  const [uploadingDocument, setUploadingDocument] = useState(false);

  // JSON output state

  // SSE state
  const [listenEventsEnabled, setListenEventsEnabled] = useState<boolean>(false);
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [streamingEvents, setStreamingEvents] = useState<WorkflowEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);

  // Ref for auto-scrolling events container
  const eventsContainerRef = useRef<HTMLDivElement>(null);

  const loadWorkflow = useCallback(async () => {
    if (!id) return;

    try {
      const response = await floConsoleService.workflowService.getWorkflow(id);
      if (response.data?.meta?.status === 'success' && response.data.data?.data) {
        const workflowData: Workflow = {
          id: response.data.data.data.id,
          name: response.data.data.data.name,
          namespace: response.data.data.data.namespace,
          created_at: response.data.data.data.created_at,
          updated_at: response.data.data.data.updated_at,
          yaml_content: response.data.data.data.yaml_content || '',
        };
        setWorkflow(workflowData);
        setYamlContent(response.data.data.data.yaml_content || '');
      }
    } catch (error) {
      console.error('Error loading workflow:', error);
    }
  }, [id]);

  const handleImageUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;

      // Validate file type
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
      const maxSize = 10 * 1024 * 1024; // 10MB

      // Validate all files before processing
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (!allowedTypes.includes(file.type)) {
          notifyError(`File ${file.name} is not a valid image type. Please select JPEG, PNG, GIF, or WebP files.`);
          return;
        }
        if (file.size > maxSize) {
          notifyError(`File ${file.name} exceeds 10MB limit`);
          return;
        }
      }

      setUploadingImage(true);

      // Process all files
      const filePromises = Array.from(files).map(
        (file) =>
          new Promise<{
            file: File;
            base64: string;
            base64Content: string;
            mimeType: string;
          }>((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = (e) => {
              const base64 = e.target?.result as string;
              const base64Content = base64.split(',')[1] || base64;
              resolve({
                file,
                base64,
                base64Content,
                mimeType: file.type,
              });
            };

            reader.onerror = () => reject(new Error(`Error reading ${file.name}`));
            reader.readAsDataURL(file);
          })
      );

      Promise.all(filePromises)
        .then((newImages) => {
          setUploadedImages((prev) => [...prev, ...newImages]);
          // Keep single image for backward compatibility (use first image)
          if (newImages.length > 0) {
            setUploadedImage({
              file: newImages[0].file,
              base64: newImages[0].base64,
              mimeType: newImages[0].mimeType,
            });
          }
          setUploadingImage(false);
          notifySuccess(`${newImages.length} image(s) uploaded successfully`);
          event.target.value = '';
          setShowUploadMenu(false);
        })
        .catch((error) => {
          notifyError(error.message || 'Error reading image files');
          setUploadingImage(false);
        });
    },
    [notifyError, notifySuccess]
  );

  const handleRemoveImage = useCallback((index: number) => {
    setUploadedImages((prev) => {
      const remaining = prev.filter((_, i) => i !== index);
      // Update single image for backward compatibility
      if (remaining.length > 0) {
        setUploadedImage({
          file: remaining[0].file,
          base64: remaining[0].base64,
          mimeType: remaining[0].mimeType,
        });
      } else {
        setUploadedImage(null);
      }
      return remaining;
    });
  }, []);

  // Cleanup fetchEventSource on unmount and when switching between SSE/normal inference
  useEffect(() => {
    return () => {
      if (abortController) {
        abortController.abort();
        setAbortController(null);
      }
    };
  }, [abortController]);
  const handleDocumentUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;

      // Validate file type
      const allowedTypes = ['application/pdf', 'text/plain'];
      const maxSize = 50 * 1024 * 1024; // 50MB

      // Validate all files before processing
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (!allowedTypes.includes(file.type)) {
          notifyError(`Invalid file type for ${file.name}. Please select PDF or TXT files only.`);
          return;
        }
        if (file.size > maxSize) {
          notifyError(`File ${file.name} is too large. Maximum size is 50MB.`);
          return;
        }
      }

      setUploadingDocument(true);

      // Process all files
      const filePromises = Array.from(files).map((file) => {
        return new Promise<{
          file: File;
          base64: string;
          base64Content: string;
          mimeType: string;
          documentType: 'pdf' | 'txt';
        }>((resolve, reject) => {
          const reader = new FileReader();

          reader.onload = (e) => {
            const dataUrl = e.target?.result as string;
            const base64 = dataUrl.split(',')[1];
            const documentType = file.type === 'application/pdf' ? 'pdf' : 'txt';

            resolve({
              file,
              base64: dataUrl,
              base64Content: base64,
              mimeType: file.type,
              documentType,
            });
          };

          reader.onerror = () => reject(new Error(`Error reading ${file.name}`));
          reader.readAsDataURL(file);
        });
      });

      Promise.all(filePromises)
        .then((newDocuments) => {
          setUploadedDocuments((prev) => [...prev, ...newDocuments]);
          setUploadingDocument(false);
          // Reset file input
          setShowUploadMenu(false);
          event.target.value = '';
        })
        .catch((error) => {
          notifyError(error.message || 'Error reading document files');
          setUploadingDocument(false);
        });
    },
    [notifyError]
  );

  const handleRemoveDocument = useCallback((index: number) => {
    setUploadedDocuments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  useEffect(() => {
    loadWorkflow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleSave = async () => {
    if (!id || !workflow) return;

    setSaving(true);
    try {
      await floConsoleService.workflowService.updateWorkflow(id, yamlContent);
      setWorkflow({ ...workflow, yaml_content: yamlContent });
      setEditDialogOpen(false);
      notifySuccess('Workflow updated successfully');
    } catch (error) {
      console.error('Error updating workflow:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleEditDialogOpen = () => {
    setEditDialogOpen(true);
  };

  const handleEditDialogClose = () => {
    setEditDialogOpen(false);
    // Reset yamlContent to original workflow content when canceling
    if (workflow) {
      setYamlContent(workflow.yaml_content || '');
    }
  };

  const handleQuertionEntered = () => {
    if (
      inferenceInput.trim().length > 0 ||
      uploadedImages.length > 0 ||
      uploadedDocuments.length > 0 ||
      uploadedImage
    ) {
      handleRunInference();
      setInferenceInput('');
      setUploadedImages([]);
      setUploadedImage(null);
      // Clear documents after inference
      setUploadedDocuments([]);
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
    if (abortController) {
      abortController.abort();
      setAbortController(null);
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

      // Prepare inputs based on what's provided
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let inputs: string | any[];

      // Handle different input combinations
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const messageInputs: any[] = [];
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
        const result = await floConsoleService.workflowService.runInference(id, inputs, variables);
        const resultContent = result.data?.data?.data?.result;
        if (resultContent) {
          setChatHistory((prev) => [...prev, { role: 'assistant', content: resultContent }]);
        }
      }
    } catch (error) {
      console.error('Error running inference:', error);
      notifyError('Failed to run inference. Please try again.');
    } finally {
      if (!listenEventsEnabled) {
        setRunningInference(false);
      }
    }
  };

  const handleSSEInference = async (inputs: string | any[], variables: Record<string, any>) => {
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
      };

      const url = `${baseUrl}/v1/${appId}/floware/v2/workflows/${id}/inference`;

      // Create abort controller for cleanup
      const controller = new AbortController();
      setAbortController(controller);

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
      setAbortController(null);
    }
  };

  return (
    <div className="h-full bg-white py-5">
      <div className="flex h-full w-full flex-col gap-10">
        <div className="flex items-center justify-between">
          <p className="text-2xl leading-normal font-semibold text-black">{workflow?.name}</p>
          <div className="flex gap-4">
            <Button variant="outline" onClick={handleEditDialogOpen}>
              Edit
            </Button>
          </div>
        </div>

        <div className="flex w-full flex-1 gap-10 pb-5">
          <div className="flex h-full w-full flex-col gap-10">
            <div className="flex h-full flex-col gap-3">
              <p className="text-lg leading-4 font-medium text-black">Configuration</p>
              <CodeMirror
                value={yamlContent}
                editable={false}
                onChange={(value: string) => setYamlContent(value)}
                theme="dark"
                className="h-full max-h-[600px] w-full max-w-[800px]"
                height="100%"
                extensions={[langs.yaml()]}
              />
            </div>
          </div>

          <div className="flex w-full flex-col gap-2">
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
              listenEventsEnabled={listenEventsEnabled}
              setListenEventsEnabled={setListenEventsEnabled}
              isModelSwitchEnabled={false}
              streamingEvents={streamingEvents}
              isStreaming={isStreaming}
              eventsContainerRef={eventsContainerRef}
            />
          </div>
        </div>
      </div>

      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Edit Workflow Configuration</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-4">
            <CodeMirror
              value={yamlContent}
              editable={true}
              onChange={(value: string) => setYamlContent(value)}
              theme="dark"
              height="500px"
              className="w-full"
              extensions={[langs.yaml()]}
            />
            <p className="text-sm leading-normal font-normal text-[#878787]">
              Define your workflow configuration in YAML format.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleEditDialogClose} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSave} loading={saving}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default WorkflowDetail;
