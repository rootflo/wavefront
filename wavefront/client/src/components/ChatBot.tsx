import { Button } from '@app/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Spinner } from '@app/components/ui/spinner';
import { Textarea } from '@app/components/ui/textarea';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import { ChatMessageContent, ImageContent, DocumentContent } from '@app/types/chat-message';
import clsx from 'clsx';
import { ChevronDown, Plus, X } from 'lucide-react';
import React, { useRef, useState, type RefObject } from 'react';
import Stream from './Stream';

// Helper function to format file size
const formatFileSize = (bytes: number): string => {
  const mb = bytes / (1024 * 1024);
  if (mb < 1) {
    const kb = bytes / 1024;
    return `${kb.toFixed(2)} KB`;
  }
  return `${mb.toFixed(2)} MB`;
};

interface ChatBotProps {
  chatHistory: { role: 'user' | 'assistant'; content: ChatMessageContent }[];
  runningInference: boolean;
  selectedLLMConfigId: string;
  setSelectedLLMConfigId: React.Dispatch<React.SetStateAction<string>>;
  loadingConfigs: boolean;
  llmConfigs: LLMInferenceConfig[];
  uploadedImages: Array<{
    file: File;
    base64: string;
    base64Content: string;
    mimeType: string;
  }>;
  uploadedDocuments: Array<{
    file: File;
    base64: string;
    base64Content: string;
    mimeType: string;
    documentType: 'pdf' | 'txt';
  }>;
  handleRemoveImage: (index: number) => void;
  handleRemoveDocument: (index: number) => void;
  showUploadMenu: boolean;
  setShowUploadMenu: React.Dispatch<React.SetStateAction<boolean>>;
  inferenceInput: string;
  setInferenceInput: React.Dispatch<React.SetStateAction<string>>;
  inferenceVariables: string;
  setInferenceVariables: React.Dispatch<React.SetStateAction<string>>;
  showVariablesInput: boolean;
  setShowVariablesInput: React.Dispatch<React.SetStateAction<boolean>>;
  handleQuestionEntered: () => void;
  handleImageUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleDocumentUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  uploadingImage: boolean;
  uploadingDocument: boolean;
  listenEventsEnabled?: boolean;
  setListenEventsEnabled?: React.Dispatch<React.SetStateAction<boolean>>;
  isModelSwitchEnabled?: boolean;
  streamingEvents?: Array<{
    event_type: string;
    timestamp: number;
    node_name?: string;
    node_type?: string;
    execution_time?: number;
    error?: string;
    router_choice?: string;
  }>;
  isStreaming?: boolean;
  eventsContainerRef?: RefObject<HTMLDivElement | null>;
}

const ChatBot = ({
  chatHistory,
  runningInference,
  selectedLLMConfigId,
  setSelectedLLMConfigId,
  loadingConfigs,
  llmConfigs,
  uploadedImages,
  uploadedDocuments,
  handleRemoveImage,
  handleRemoveDocument,
  showUploadMenu,
  setShowUploadMenu,
  inferenceInput,
  setInferenceInput,
  inferenceVariables,
  setInferenceVariables,
  showVariablesInput,
  setShowVariablesInput,
  handleQuestionEntered,
  handleImageUpload,
  handleDocumentUpload,
  uploadingImage,
  uploadingDocument,
  listenEventsEnabled,
  setListenEventsEnabled,
  streamingEvents,
  isStreaming,
  eventsContainerRef,
  isModelSwitchEnabled = true,
}: ChatBotProps) => {
  const variablesModalRef = useRef<HTMLDivElement>(null);
  const [showLogic, setShowLogic] = useState(false);
  const [selectValue, setSelectValue] = useState<string>('');

  return (
    <div className="flex h-full w-full flex-col gap-7">
      <div className="flex flex-col justify-between gap-2">
        {listenEventsEnabled !== undefined && setListenEventsEnabled !== undefined && (
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-700">Real-time Events</label>
              <button
                type="button"
                onClick={() => setListenEventsEnabled(!listenEventsEnabled)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:outline-none ${
                  listenEventsEnabled ? 'bg-blue-600' : 'bg-gray-200'
                }`}
                role="switch"
                aria-checked={listenEventsEnabled}
                aria-label="Toggle real-time events"
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    listenEventsEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {listenEventsEnabled ? 'Stream real-time workflow execution events' : 'Standard inference response only'}
            </p>
          </div>
        )}
      </div>

      <div className="flex w-full flex-1 flex-col justify-between gap-2 rounded-xl border border-[#EFF0F1] bg-[#FBFBFB] p-2 font-mono text-sm font-normal outline-none">
        <div id="message-container" className="h-full space-y-4 overflow-auto bg-white p-4">
          {chatHistory.map((chat, index) => (
            <div key={index} className={`flex w-full ${chat.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={clsx('flex max-w-[70%] flex-col', index % 2 === 0 ? 'items-end' : 'items-start')}>
                <div
                  className={clsx(
                    'rounded-lg p-3 wrap-break-word break-all whitespace-pre-wrap',
                    chat.role === 'user' ? 'bg-blue-100 text-blue-900' : 'bg-gray-100 text-gray-900'
                  )}
                >
                  {typeof chat.content === 'string' ? (
                    chat.content
                  ) : typeof chat.content === 'object' && chat.content !== null && 'image_base64' in chat.content ? (
                    <div className="flex items-center gap-2">
                      <img
                        src={`data:${(chat.content as ImageContent).mime_type || 'image/png'};base64,${(chat.content as ImageContent).image_base64}`}
                        alt="Uploaded"
                        className="h-4 w-4 rounded object-cover"
                      />
                      <p className="max-w-[120px] truncate text-[8px] font-medium text-gray-800">
                        Image ({(chat.content as ImageContent).mime_type || 'unknown'})
                      </p>
                    </div>
                  ) : typeof chat.content === 'object' && chat.content !== null && 'document_type' in chat.content ? (
                    <div className="flex items-center gap-2">
                      <span>📄</span>
                      <span>{(chat.content as DocumentContent).metadata?.filename || 'Document'}</span>
                    </div>
                  ) : (
                    JSON.stringify(chat.content, null, 2)
                  )}
                </div>
                <p className={`mt-1 text-[8px] text-gray-500 ${chat.role === 'user' ? 'text-right' : 'text-left'}`}>
                  {chat.role === 'user' ? 'You' : 'Agent'}
                </p>
              </div>
            </div>
          ))}
          {listenEventsEnabled &&
            ((streamingEvents && streamingEvents.length > 0) || (chatHistory && chatHistory.length > 0)) && (
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => setShowLogic(!showLogic)}
                  className="flex w-full items-center justify-between rounded-md bg-gray-200 p-1 text-xs font-medium"
                >
                  <p className="text-xs font-medium">{showLogic ? 'Hide events' : 'Show events'}</p>
                  <div className={clsx(showLogic ? 'rotate-180' : '')}>
                    <ChevronDown />
                  </div>
                </button>
                {showLogic && streamingEvents && streamingEvents.length > 0 && (
                  <Stream
                    listenEventsEnabled={listenEventsEnabled}
                    streamingEvents={streamingEvents}
                    isStreaming={isStreaming}
                    eventsContainerRef={eventsContainerRef}
                  />
                )}
              </div>
            )}
          {runningInference && (
            <div className="flex w-max">
              <Spinner />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 border-gray-200 pt-2">
          {/* Fixed Model Selection */}
          {isModelSwitchEnabled && (
            <div className="w-max min-w-[150px] shrink-0">
              <Select
                value={selectedLLMConfigId || undefined}
                onValueChange={(value) => setSelectedLLMConfigId(value)}
                disabled={loadingConfigs}
              >
                <SelectTrigger className="h-auto w-full rounded-lg border border-[#EFF0F1] bg-white p-1 text-[10px] text-black outline-none">
                  <SelectValue placeholder="default model" />
                </SelectTrigger>
                <SelectContent>
                  {llmConfigs.map((config) => (
                    <SelectItem key={config.id} value={config.id}>
                      {config.display_name} ({config.type})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Scrollable Attachments Container */}
          {(uploadedImages.length > 0 || uploadedDocuments.length > 0) && (
            <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
              {/* Uploaded Images */}
              {uploadedImages.length > 0 && (
                <div className="flex shrink-0 gap-2">
                  {uploadedImages.map((image, index) => (
                    <div
                      key={index}
                      className="group relative flex items-center gap-1 rounded-lg border border-gray-200 bg-white p-1 transition-colors hover:border-gray-300"
                    >
                      <img src={image.base64} alt={image.file.name} className="h-6 w-6 rounded object-cover" />
                      <div className="flex flex-col">
                        <p className="max-w-[120px] truncate text-[8px] font-medium text-gray-800">{image.file.name}</p>
                        <p className="text-[8px] text-gray-500">{formatFileSize(image.file.size)}</p>
                      </div>
                      <button
                        onClick={() => handleRemoveImage(index)}
                        className="ml-2 text-red-500 transition-colors hover:text-red-700"
                        title="Remove image"
                      >
                        <X />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Uploaded Documents */}
              {uploadedDocuments.length > 0 && (
                <div className="flex shrink-0 gap-2">
                  {uploadedDocuments.map((doc, index) => (
                    <div
                      key={index}
                      className="group relative flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-2 transition-colors hover:border-gray-300"
                    >
                      <div className="text-gray-600">📄</div>
                      <div className="flex flex-col">
                        <p className="max-w-[120px] truncate text-[8px] font-medium text-gray-800">{doc.file.name}</p>
                        <p className="text-[8px] text-gray-500">{formatFileSize(doc.file.size)}</p>
                      </div>
                      <button
                        onClick={() => handleRemoveDocument(index)}
                        className="ml-2 text-red-500 transition-colors hover:text-red-700"
                        title="Remove document"
                      >
                        <X />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="relative flex w-full gap-2">
          <input
            type="file"
            id="imageInput"
            accept="image/*"
            onChange={handleImageUpload}
            className="hidden"
            disabled={uploadingImage}
            multiple
          />
          <input
            type="file"
            id="documentInput"
            accept=".pdf,.txt,application/pdf,text/plain"
            onChange={handleDocumentUpload}
            className="hidden"
            disabled={uploadingDocument}
            multiple
          />
          {showVariablesInput && (
            <div
              ref={variablesModalRef}
              className="absolute -top-[332px] left-0 z-20 flex w-96 flex-col gap-4 rounded-xl border border-[#EFF0F1] bg-white p-4 shadow-xl"
            >
              <div className="flex items-center justify-between">
                <label htmlFor="variables" className="text-base leading-normal font-normal text-[#282828]">
                  Variables (JSON)
                </label>
                <button
                  onClick={() => setShowVariablesInput(false)}
                  className="cursor-pointer text-gray-400 transition-colors hover:text-gray-600"
                >
                  <X />
                </button>
              </div>
              <textarea
                id="variables"
                value={inferenceVariables}
                onChange={(e) => setInferenceVariables(e.target.value)}
                rows={5}
                className="w-full rounded-lg border border-gray-300 bg-white p-3 font-mono text-sm text-[#282828] outline-none focus:text-black"
                placeholder='{"key": "value"}'
              />
              <p className="text-sm leading-normal font-normal text-[#878787]">
                Define your variables in JSON format. Variables will be passed to the agent during inference.
              </p>
              <Button
                onClick={() => setShowVariablesInput(false)}
                className="cursor-pointer rounded-xl bg-[#101010]! px-4 py-3 text-white!"
              >
                Done
              </Button>
            </div>
          )}
          <div className="flex flex-col items-center justify-center">
            <Select
              value={selectValue}
              onValueChange={(value) => {
                setSelectValue('');
                setShowUploadMenu(false);
                if (value === 'images') {
                  document.getElementById('imageInput')?.click();
                } else if (value === 'documents') {
                  document.getElementById('documentInput')?.click();
                } else if (value === 'variables') {
                  setShowVariablesInput(true);
                }
              }}
              open={showUploadMenu}
              onOpenChange={setShowUploadMenu}
            >
              <SelectTrigger className="inline-flex cursor-pointer rounded-md border-0 bg-transparent text-sm font-medium whitespace-nowrap text-gray-900 shadow-none ring-0 transition-all outline-none focus:ring-0 focus:outline-none focus-visible:ring-0 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&>span]:hidden [&>svg:last-child]:hidden">
                <Plus />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="images">Select Images</SelectItem>
                <SelectItem value="documents">Select Documents</SelectItem>
                <SelectItem value="variables">Add variables</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="w-full">
            <div className="flex w-full resize-none items-center justify-between rounded-lg border border-gray-300 bg-white p-2 text-sm text-[#282828] outline-none focus:text-black">
              <Textarea
                value={inferenceInput}
                onChange={(e) => setInferenceInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleQuestionEntered();
                  }
                }}
                rows={4}
                className="flex-1 resize-none border-0 bg-transparent shadow-none outline-none focus-visible:ring-0"
                placeholder="Ask anything"
              />
              <button
                type="button"
                onClick={handleQuestionEntered}
                className="h-max w-max rounded-full bg-blue-600 p-2 text-white hover:bg-blue-700"
              >
                <svg className="h-4 w-4 rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
export default ChatBot;
