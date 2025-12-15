import floConsoleService from '@app/api';
import ChatBot from '@app/components/ChatBot';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { useDeleteAgent } from '@app/hooks';
import { useGetAgent, useGetLLMConfigs, useGetTools } from '@app/hooks/data/fetch-hooks';
import { getAgentKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { scrollToBottom } from '@app/utils/scroll';
import { useQueryClient } from '@tanstack/react-query';
import yaml from 'js-yaml';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import EditAgentDialog from './EditAgentDialog';

const AgentDetail: React.FC = () => {
  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [showUploadMenu, setShowUploadMenu] = useState(false);
  const [showVariablesInput, setShowVariablesInput] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
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

  // Image upload state
  const [uploadedImages, setUploadedImages] = useState<
    Array<{
      file: File;
      base64: string; // Full data URL for display
      base64Content: string; // Just base64 content for API
      mimeType: string;
    }>
  >([]);
  const [uploadingImage, setUploadingImage] = useState(false);

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
  const [chatHistory, setChatHistory] = useState<{ role: 'user' | 'assistant'; content: any }[]>([]);

  // Datasource and tool selection state
  const [selectedTools, setSelectedTools] = useState<{ id: string; value: string }[]>([]);
  const isUpdatingYamlRef = useRef(false);

  // Fetch data using hooks
  const { data: agent, isLoading: agentLoading } = useGetAgent(appId, id);
  const { data: llmConfigs = [], isLoading: loadingConfigs } = useGetLLMConfigs(appId);
  const { data: availableTools = [] } = useGetTools(appId);
  const deleteAgentMutation = useDeleteAgent(appId);

  // Update yaml content when agent data changes
  useEffect(() => {
    if (agent?.yaml_content) {
      isUpdatingYamlRef.current = true;
      setYamlContent(agent.yaml_content);
      // Reset flag after state update
      setTimeout(() => {
        isUpdatingYamlRef.current = false;
      }, 0);
    }
  }, [agent]);

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

  const handleQuestionEntered = () => {
    if (inferenceInput.trim().length > 0) {
      handleRunInference();
      setInferenceInput('');
      requestAnimationFrame(() => {
        setTimeout(() => scrollToBottom('message-container', 'smooth'), 150);
      });
    }
  };

  useEffect(() => {
    // Skip if we're updating YAML from agent data or if dependencies are not ready
    if (isUpdatingYamlRef.current || !yamlContent || toolsDetails.length === 0) return;

    const tools = toolsDetails.filter((tool) => selectedTools.some((selected) => selected.value === tool.display_name));
    const parsedYaml = yaml.load(yamlContent) as any;
    if (parsedYaml && parsedYaml.agent) {
      if (!parsedYaml.agent.tools) {
        parsedYaml.agent.tools = [];
      }

      // Clear existing tools and add new ones
      const newTools = tools.map((tool) => {
        // Merge all prefilled_values objects into a single object
        const prefilledParams: Record<string, string> | undefined =
          tool.prefilled_values && tool.prefilled_values.length > 0
            ? tool.prefilled_values.reduce(
                (acc: Record<string, string>, obj: { [key: string]: string }) => {
                  // Each obj is like { datasource_id: "value" }
                  return { ...acc, ...obj };
                },
                {} as Record<string, string>
              )
            : undefined;

        return {
          name: tool.name,
          prefilled_params: prefilledParams,
          name_override: tool.name,
          description_override: tool.description,
        };
      });

      // Compare existing tools with new tools to avoid unnecessary updates
      const existingTools = parsedYaml.agent.tools || [];
      const toolsChanged =
        existingTools.length !== newTools.length ||
        existingTools.some((existingTool: any, index: number) => {
          const newTool = newTools[index];
          if (!newTool) return true;
          return (
            existingTool.name !== newTool.name ||
            JSON.stringify(existingTool.prefilled_params || {}) !== JSON.stringify(newTool.prefilled_params || {})
          );
        });

      // Only update if tools actually changed
      if (toolsChanged) {
        parsedYaml.agent.tools = newTools;
        const newYamlContent = yaml.dump(parsedYaml);
        // Only update if the YAML string actually changed
        if (newYamlContent !== yamlContent) {
          isUpdatingYamlRef.current = true;
          setYamlContent(newYamlContent);
          // Reset flag after state update
          setTimeout(() => {
            isUpdatingYamlRef.current = false;
          }, 0);
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTools, toolsDetails]);

  const handleImageUpload = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
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
            // Extract just the base64 content without the data URL prefix
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
        setUploadingImage(false);
        notifySuccess(`${newImages.length} image(s) uploaded successfully`);
        // Reset file input
        event.target.value = '';
        // Close the upload menu after successful upload
        setShowUploadMenu(false);
      })
      .catch((error) => {
        notifyError(error.message || 'Error reading image files');
        setUploadingImage(false);
      });
  }, []);

  const handleRemoveImage = useCallback((index: number) => {
    setUploadedImages((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleDocumentUpload = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
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
        notifySuccess(`${newDocuments.length} document(s) uploaded successfully`);
        // Reset file input
        event.target.value = '';
        // Close the upload menu after successful upload
        setShowUploadMenu(false);
      })
      .catch((error) => {
        notifyError(error.message || 'Error reading document files');
        setUploadingDocument(false);
      });
  }, []);

  const handleRemoveDocument = useCallback((index: number) => {
    setUploadedDocuments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSave = async (yamlContent: string) => {
    if (!appId || !id || !agent) return;

    setSaving(true);
    try {
      await floConsoleService.agentService.updateAgent(id, yamlContent);
      // Invalidate agent query to refetch updated data
      queryClient.invalidateQueries({
        queryKey: getAgentKey(appId || '', id || ''),
      });
      notifySuccess('Agent updated successfully');
    } catch (error) {
      console.error('Error updating agent:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteClick = () => {
    if (agent) {
      setDeleteItem({ id: agent.id, name: agent.name });
    }
  };

  const handleDeleteConfirm = async () => {
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let inputs: string | any[];
      const finalTextInput = inferenceInput.trim();
      // Handle different input combinations
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const conversationInputs: any[] = [];

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
      const result = await floConsoleService.agentService.runInference(
        id,
        variables,
        inputs,
        selectedLLMConfigId || undefined,
        selectedTools.length > 0 ? selectedTools.map((tool) => tool.value) : undefined
      );
      const responseData = (result as any).data?.data?.data;
      const agentResponse =
        typeof responseData?.result === 'string' ? responseData.result : JSON.stringify(responseData?.result, null, 2);
      setChatHistory((prev) => [...prev, { role: 'assistant', content: agentResponse }]);
      // Wait for DOM to update before scrolling
      requestAnimationFrame(() => {
        setTimeout(() => scrollToBottom('message-container', 'smooth'), 150);
      });
      //clearing the documents and images
      setUploadedDocuments([]);
      setUploadedImages([]);
    } catch (error) {
      console.error('Error running inference:', error);
    } finally {
      setRunningInference(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white p-8">
      <Breadcrumb className="mb-6">
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
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{agent?.name}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {agentLoading ? (
        <div className="flex items-center justify-center p-8">Loading agent...</div>
      ) : !agent ? (
        <div className="flex items-center justify-center p-8 text-red-600">Agent not found</div>
      ) : (
        <>
          <div className="flex w-full flex-1 flex-col gap-10">
            <div className="flex items-start justify-between">
              <p className="text-2xl leading-normal font-semibold text-black">{agent.name}</p>
              <div className="flex gap-4">
                <Button variant="outline" onClick={() => setEditDialogOpen(true)}>
                  Edit
                </Button>
                <Button variant="destructive" onClick={handleDeleteClick}>
                  Delete
                </Button>
              </div>
            </div>
          </div>

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
          />

          {/* Edit Agent Dialog */}
          <EditAgentDialog
            isOpen={editDialogOpen}
            onOpenChange={setEditDialogOpen}
            yamlContent={yamlContent}
            selectedTools={selectedTools}
            toolsDetails={toolsDetails}
            onSave={async (updatedYamlContent, updatedSelectedTools) => {
              setYamlContent(updatedYamlContent);
              setSelectedTools(updatedSelectedTools);
              handleSave(updatedYamlContent);
            }}
            saving={saving}
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
