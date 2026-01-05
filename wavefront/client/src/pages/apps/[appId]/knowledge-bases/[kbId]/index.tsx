import floConsoleService from '@app/api';
import { NewInferencePayload } from '@app/api/knowledge-base-service';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { Textarea } from '@app/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@app/components/ui/tooltip';
import {
  getKnowledgeBaseDocumentsKey,
  getKnowledgeBaseInferencesKey,
  useGetKnowledgeBase,
  useGetKnowledgeBaseDocuments,
  useGetKnowledgeBaseInferences,
  useGetLLMConfigs,
} from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { PlayIcon, Send, TrashIcon } from 'lucide-react';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';

const KnowledgeBaseDetailPage: React.FC = () => {
  const { kbId, app: appId } = useParams<{ kbId: string; app: string }>();

  const [showDeleteInferenceModal, setShowDeleteInferenceModal] = useState<boolean>(false);
  const [inferenceToDelete, setInferenceToDelete] = useState<string | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [documentToDelete, setDocumentToDelete] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  // Create System Prompt Dialog state
  const [showCreatePromptModal, setShowCreatePromptModal] = useState<boolean>(false);
  const [systemPrompt, setSystemPrompt] = useState<string>('');
  const [selectedConfigId, setSelectedConfigId] = useState<string | null>(null);
  const [creatingPrompt, setCreatingPrompt] = useState<boolean>(false);

  // Test Inference Dialog state
  const [showTestInferenceModal, setShowTestInferenceModal] = useState<boolean>(false);
  const [testInferenceId, setTestInferenceId] = useState<string | null>(null);
  const [testQuery, setTestQuery] = useState<string>('');
  const [chatMessages, setChatMessages] = useState<
    Array<{ role: 'user' | 'assistant'; content: string; sources?: unknown[] }>
  >([]);
  const [loadingRag, setLoadingRag] = useState<boolean>(false);
  const [messagesContainerRef, setMessagesContainerRef] = useState<HTMLDivElement | null>(null);

  const { data: knowledgeBase } = useGetKnowledgeBase(appId, kbId);
  const { data: documents = [], isLoading: loadingDocs } = useGetKnowledgeBaseDocuments(appId, kbId);
  const { data: inferences = [], isLoading: loadingInferences } = useGetKnowledgeBaseInferences(appId, kbId);
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const handleFileUpload = async () => {
    if (!file || !kbId || !appId) {
      notifyError('File, Knowledge Base ID, or Service not available.');
      return;
    }
    setUploading(true);
    try {
      await floConsoleService.knowledgeBaseService.uploadDocument(kbId, file);
      notifySuccess(`${file.name} uploaded successfully.`);
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseDocumentsKey(appId || '', kbId || '') });
      setShowUploadModal(false);
    } catch (error) {
      console.error('File upload failed:', error);
      notifyError(`Failed to upload ${file.name}.`);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (!kbId || !appId) {
      notifyError('Knowledge Base ID or Service not available.');
      return;
    }

    try {
      await floConsoleService.knowledgeBaseService.deleteDocument(kbId, documentId);
      notifySuccess('Document deleted successfully.');
      // Invalidate queries to refresh document list
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseDocumentsKey(appId || '', kbId || '') });
    } catch (error) {
      console.error('Document deletion failed:', error);
      notifyError('Failed to delete document.');
    }
  };

  const handleDeleteInference = async (inferenceId: string) => {
    if (!kbId || !appId) {
      notifyError('Knowledge Base ID or Service not available.');
      return;
    }

    try {
      await floConsoleService.knowledgeBaseService.deleteSystemPrompt(kbId, inferenceId);
      notifySuccess('Inference deleted successfully.');
      // Invalidate queries to refresh inferences list
      queryClient.invalidateQueries({ queryKey: getKnowledgeBaseInferencesKey(appId || '', kbId || '') });
    } catch (error) {
      console.error('Inference deletion failed:', error);
      notifyError('Failed to delete inference.');
    }
  };

  const handleCreateSystemPrompt = async () => {
    if (!kbId || !appId || !systemPrompt) {
      notifyError('Knowledge Base ID, Service, or System Prompt not available.');
      return;
    }
    if (!selectedConfigId) {
      notifyError('Please choose an LLM configuration before saving.');
      return;
    }
    setCreatingPrompt(true);
    try {
      const payload: NewInferencePayload = { prompt: systemPrompt };
      const response = await floConsoleService.knowledgeBaseService.createSystemPrompt(kbId, payload, selectedConfigId);
      if (response.data && response.data.data) {
        notifySuccess('System prompt created successfully.');
        // Invalidate queries to refresh inferences list
        queryClient.invalidateQueries({ queryKey: getKnowledgeBaseInferencesKey(appId || '', kbId || '') });
        setShowCreatePromptModal(false);
        setSystemPrompt('');
        setSelectedConfigId(null);
      } else {
        notifyError('Failed to create system prompt.');
      }
    } catch (error) {
      console.error('Failed to create system prompt:', error);
      notifyError('Error creating system prompt.');
    } finally {
      setCreatingPrompt(false);
    }
  };

  const handleCloseCreatePromptModal = () => {
    setShowCreatePromptModal(false);
    setSystemPrompt('');
    setSelectedConfigId(null);
  };

  const handleOpenTestInference = (inferenceId: string) => {
    setTestInferenceId(inferenceId);
    setTestQuery('');
    setChatMessages([]);
    setShowTestInferenceModal(true);
  };

  const handleCloseTestInferenceModal = () => {
    setShowTestInferenceModal(false);
    setTestInferenceId(null);
    setTestQuery('');
    setChatMessages([]);
  };

  const scrollToBottom = () => {
    if (messagesContainerRef) {
      messagesContainerRef.scrollTop = messagesContainerRef.scrollHeight;
    }
  };

  const handleTestRagQuery = async () => {
    if (!kbId || !testInferenceId || !appId) {
      notifyError('Knowledge Base ID, Inference ID, or Service not available.');
      return;
    }
    if (!testQuery.trim()) {
      notifyError('Please enter a query.');
      return;
    }

    // Add user message to chat
    const userMessage = testQuery.trim();
    setChatMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setTestQuery('');
    setLoadingRag(true);

    // Scroll to bottom after user message is added
    setTimeout(() => scrollToBottom(), 100);

    try {
      const response = await floConsoleService.knowledgeBaseService.ragQuery(kbId, testInferenceId, userMessage);

      if (response.data?.data) {
        const responseData = response.data.data;
        // Add assistant response to chat
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: responseData.response || 'No response received.',
            sources: responseData.sources,
          },
        ]);
        // Scroll to bottom after response is added
        setTimeout(() => scrollToBottom(), 100);
      } else {
        notifyError('Failed to get RAG response.');
        setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Failed to get response.' }]);
      }
    } catch (error) {
      console.error('RAG query failed:', error);
      notifyError('Failed to get RAG response.');
      setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Error: Failed to get response.' }]);
    } finally {
      setLoadingRag(false);
    }
  };

  return (
    <div className="h-full bg-white px-8 pt-8 pb-[200px]">
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
                onClick={() => navigate(`/apps/${appId}/knowledge-bases`)}
                className="hover:text-foreground cursor-pointer"
              >
                Knowledge Bases
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{knowledgeBase?.name || kbId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex w-full flex-col gap-6 pb-4">
        <div className="flex items-center justify-between">
          <p className="text-2xl leading-normal font-semibold text-black">{knowledgeBase?.name || 'N/A'}</p>
        </div>
        <div className="grid w-full grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="flex w-full flex-col gap-6">
            <div className="flex w-full items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Documents</h3>
              <Button variant="outline" onClick={() => setShowUploadModal(true)}>
                Upload Document
              </Button>
            </div>

            {loadingDocs ? (
              <div className="flex flex-col items-start gap-4 rounded-lg border border-gray-200 bg-gray-50 p-6">
                <p className="text-sm font-medium text-gray-600">Loading</p>
                <div className="text-sm text-black">Loading documents...</div>
              </div>
            ) : documents.length === 0 ? (
              <div className="flex flex-col items-start gap-4 rounded-lg border border-gray-200 bg-gray-50 p-6">
                <p className="text-sm font-medium text-gray-600">No Documents</p>
                <div className="text-sm text-black">No documents uploaded yet.</div>
              </div>
            ) : (
              <div className="rounded-lg border border-gray-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Document Name</TableHead>
                      <TableHead>Uploaded Date</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell className="font-medium">
                          {doc.file_name}
                          <span className="ml-2 text-xs text-gray-500">({doc.file_type})</span>
                        </TableCell>
                        <TableCell>{dayjs(doc.updated_at).format('DD MMM YYYY')}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setDocumentToDelete(doc.id);
                              setShowDeleteModal(true);
                            }}
                          >
                            <TrashIcon color="#E22F2F" className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>

          <div className="flex w-full flex-col gap-6">
            <div className="flex w-full items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">System Prompts</h3>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setShowCreatePromptModal(true)}>
                  Add System Prompt
                </Button>
              </div>
            </div>

            {loadingInferences ? (
              <div className="flex flex-col items-start gap-4 rounded-lg border border-gray-200 bg-gray-50 p-6">
                <p className="text-sm font-medium text-gray-600">Loading</p>
                <div className="text-sm text-black">Loading inferences...</div>
              </div>
            ) : inferences.length === 0 ? (
              <div className="flex flex-col items-start gap-4 rounded-lg border border-gray-200 bg-gray-50 p-6">
                <p className="text-sm font-medium text-gray-600">No Inferences</p>
                <div className="text-sm text-black">No inferences created yet.</div>
              </div>
            ) : (
              <div className="rounded-lg border border-gray-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Prompt</TableHead>
                      <TableHead>Created Date</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {inferences.map((inference) => (
                      <TableRow key={inference.inference_id}>
                        <TableCell className="max-w-[200px] truncate font-medium">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="cursor-help">{inference.inference_content}</span>
                              </TooltipTrigger>
                              <TooltipContent className="bg-black/80" side="left">
                                <p className="max-w-xs">{inference.inference_content}</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </TableCell>
                        <TableCell>
                          {inference.created_at ? dayjs(inference.created_at).format('DD MMM YYYY') : 'N/A'}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setInferenceToDelete(inference.inference_id);
                                setShowDeleteInferenceModal(true);
                              }}
                            >
                              <TrashIcon color="#E22F2F" className="h-4 w-4" />
                            </Button>

                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleOpenTestInference(inference.inference_id)}
                              title="Inference"
                            >
                              <PlayIcon className="h-4 w-4 text-green-600" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Upload Document Dialog */}
      <Dialog open={showUploadModal} onOpenChange={setShowUploadModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>Upload a document to this knowledge base</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div>
              <Label htmlFor="documentUpload" className="mb-2">
                Select Document
              </Label>
              <Input
                type="file"
                id="documentUpload"
                accept=".pdf,.txt,application/pdf,text/plain"
                onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
                disabled={uploading}
                className="w-full cursor-pointer border border-gray-300 bg-white px-3 py-2 text-sm text-black outline-none file:cursor-pointer file:text-blue-500"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadModal(false)} disabled={uploading}>
              Cancel
            </Button>
            <Button onClick={handleFileUpload} disabled={uploading}>
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={showDeleteModal}
        title="Delete Document"
        message="Are you sure you want to delete this document? This action cannot be undone."
        onConfirm={async () => {
          if (documentToDelete) {
            await handleDeleteDocument(documentToDelete);
            setShowDeleteModal(false);
            setDocumentToDelete(null);
          }
        }}
        onCancel={() => {
          setShowDeleteModal(false);
          setDocumentToDelete(null);
        }}
      />

      {/* Delete Inference Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={showDeleteInferenceModal}
        title="Delete Inference"
        message={`Are you sure you want to delete this system prompt? This action cannot be undone.`}
        onConfirm={async () => {
          if (inferenceToDelete) {
            await handleDeleteInference(inferenceToDelete);
            setShowDeleteInferenceModal(false);
            setInferenceToDelete(null);
          }
        }}
        onCancel={() => {
          setShowDeleteInferenceModal(false);
          setInferenceToDelete(null);
        }}
      />

      {/* Create System Prompt Dialog */}
      <Dialog open={showCreatePromptModal} onOpenChange={setShowCreatePromptModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create System Prompt</DialogTitle>
            <DialogDescription>
              Enter the system prompt for your LLM. This will define the behavior of the RAG inference.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div>
              <Label htmlFor="llm-config" className="mb-2">
                Select LLM Model <span className="text-red-500">*</span>
              </Label>
              <Select
                value={selectedConfigId ?? undefined}
                onValueChange={(value) => setSelectedConfigId(value ?? null)}
                disabled={llmConfigs.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select an LLM configuration" />
                </SelectTrigger>
                <SelectContent>
                  {llmConfigs.length === 0 ? (
                    <SelectItem value="" disabled>
                      No configurations available
                    </SelectItem>
                  ) : (
                    llmConfigs.map((config) => (
                      <SelectItem key={config.id} value={config.id}>
                        {config.display_name} ({config.type})
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              <p className="mt-1 text-xs text-gray-500">
                {llmConfigs.length > 0
                  ? 'Choose which LLM configuration to use for this system prompt.'
                  : 'Add an LLM configuration to create system prompts.'}
              </p>
            </div>

            <div>
              <Label htmlFor="systemPrompt" className="mb-2">
                System Prompt <span className="text-red-500">*</span>
              </Label>
              <Textarea
                id="systemPrompt"
                rows={10}
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder="e.g., You are a helpful assistant that answers questions based on the provided context..."
                className="font-mono"
              />
              <p className="mt-1 text-xs text-gray-500">
                Define the behavior and instructions for the LLM when processing RAG queries.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCloseCreatePromptModal} disabled={creatingPrompt}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateSystemPrompt}
              disabled={creatingPrompt || !systemPrompt.trim() || !selectedConfigId}
              loading={creatingPrompt}
            >
              {creatingPrompt ? 'Creating...' : 'Create Prompt'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/*Inference Dialog */}
      <Dialog
        open={showTestInferenceModal}
        onOpenChange={(open) => {
          if (!open) {
            handleCloseTestInferenceModal();
          } else {
            setShowTestInferenceModal(true);
          }
        }}
      >
        <DialogContent className="flex h-[90vh] max-h-[90vh] flex-col lg:max-w-4xl">
          <DialogHeader>
            <DialogTitle>RAG Inference</DialogTitle>
            <DialogDescription>Chat with your Knowledge Base</DialogDescription>
          </DialogHeader>

          {/* Chat Messages Container */}
          <div
            ref={setMessagesContainerRef}
            className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4"
          >
            {chatMessages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-gray-500">
                Start a conversation by asking a question...
              </div>
            ) : (
              chatMessages.map((message, index) => (
                <div key={index} className={`flex w-full ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`flex max-w-[80%] flex-col rounded-lg p-3 ${
                      message.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'border border-gray-200 bg-white text-gray-900'
                    }`}
                  >
                    <div className="text-sm whitespace-pre-wrap">{message.content}</div>
                    {message.sources && message.sources.length > 0 && message.role === 'assistant' && (
                      <div className="mt-2 border-t border-gray-200 pt-2">
                        <p className="text-xs font-medium text-gray-600">Sources:</p>
                        <ul className="mt-1 list-disc pl-4 text-xs text-gray-500">
                          {message.sources.map((source, idx) => (
                            <li key={idx} className="truncate">
                              {typeof source === 'string' ? source : JSON.stringify(source)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}

            {/* Loading Indicator */}
            {loadingRag && (
              <div className="flex w-full justify-start">
                <div className="flex max-w-[80%] flex-col rounded-lg border border-gray-200 bg-white p-3">
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"></div>
                    <span>Getting response...</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input Area */}
          <div className="mt-4 flex items-end gap-2 border-t border-gray-200 pt-4">
            <Textarea
              id="testQuery"
              value={testQuery}
              onChange={(e) => setTestQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !loadingRag && testQuery.trim()) {
                  e.preventDefault();
                  handleTestRagQuery();
                }
              }}
              placeholder="Type your message... (Press Enter to send, Shift+Enter for new line)"
              className="min-h-[60px] resize-none"
              rows={2}
              disabled={loadingRag}
            />
            <Button
              onClick={handleTestRagQuery}
              disabled={loadingRag || !testQuery.trim()}
              size="icon"
              className="h-[60px] w-[60px] shrink-0"
            >
              {loadingRag ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
              ) : (
                <Send className="h-5 w-5" />
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KnowledgeBaseDetailPage;
