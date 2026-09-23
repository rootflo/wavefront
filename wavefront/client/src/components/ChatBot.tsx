import { Button } from '@app/components/ui/button';
import { Label } from '@app/components/ui/label';
import { Switch } from '@app/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Spinner } from '@app/components/ui/spinner';
import { Textarea } from '@app/components/ui/textarea';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { DOCUMENT_ACCEPT_ATTRIBUTE, IMAGE_ACCEPT_ATTRIBUTE } from '@app/constants/upload';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import { ChatMessageContent, ImageContent, DocumentContent } from '@app/types/chat-message';
import clsx from 'clsx';
import { ChevronDown, Plus, X } from 'lucide-react';
import React, { useRef, useState, type RefObject } from 'react';
import Stream from './Stream';

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
    documentType: string;
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
  const [showLogic, setShowLogic] = useState(true);
  const [selectValue, setSelectValue] = useState<string>('');
  const combinedAttachments = [
    ...uploadedImages.map((image, index) => ({ kind: 'image' as const, image, originalIndex: index })),
    ...uploadedDocuments.map((document, index) => ({ kind: 'document' as const, document, originalIndex: index })),
  ];
  const visibleCombinedAttachments = combinedAttachments.slice(0, 2);
  const remainingCombinedAttachmentsCount = Math.max(combinedAttachments.length - visibleCombinedAttachments.length, 0);
  const remainingCombinedAttachments = combinedAttachments.slice(2);

  return (
    <div className="flex h-full w-full flex-col gap-7">
      <div className="flex flex-col justify-between gap-2">
        {listenEventsEnabled !== undefined && setListenEventsEnabled !== undefined && (
          <div>
            <div className="flex items-center justify-between">
              <Label htmlFor="realtime-events-toggle" className="frost-text text-sm font-medium">
                Real-time Events
              </Label>
              <Switch
                id="realtime-events-toggle"
                checked={listenEventsEnabled}
                onCheckedChange={setListenEventsEnabled}
              />
            </div>
            <p className="frost-text-muted mt-1 text-xs">
              {listenEventsEnabled ? 'Stream real-time workflow execution events' : 'Standard inference response only'}
            </p>
          </div>
        )}
      </div>

      <div className="frost-panel ring-frost-border flex w-full flex-1 flex-col justify-between gap-2 rounded-xl border p-2 font-mono text-sm font-normal ring-1 outline-none">
        <div id="message-container" className="frost-content h-full space-y-4 overflow-auto rounded-lg p-4">
          {chatHistory.map((chat, index) => (
            <div key={index} className={`flex w-full ${chat.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={clsx('flex max-w-[70%] flex-col', index % 2 === 0 ? 'items-end' : 'items-start')}>
                <div
                  className={clsx(
                    'rounded-lg p-3 wrap-break-word break-all whitespace-pre-wrap',
                    chat.role === 'user'
                      ? 'bg-brand/15 text-brand ring-brand/25 ring-1'
                      : 'frost-glass-strong frost-text ring-frost-border ring-1'
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
                      <p className="frost-text max-w-[120px] truncate text-[8px] font-medium">
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
                <p className={`frost-text-subtle mt-1 text-[8px] ${chat.role === 'user' ? 'text-right' : 'text-left'}`}>
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
                  className="frost-control frost-text ring-frost-border flex w-full items-center justify-between rounded-md border p-1 text-xs font-medium ring-1"
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
        <div className="border-frost-border flex items-center gap-2 border-t pt-2">
          {isModelSwitchEnabled && (
            <div className="w-max min-w-[150px] shrink-0">
              <Select
                value={selectedLLMConfigId || undefined}
                onValueChange={(value) => setSelectedLLMConfigId(value)}
                disabled={loadingConfigs}
              >
                <SelectTrigger className="frost-control frost-text ring-frost-border h-auto w-full rounded-lg border p-1 text-[10px] ring-1 outline-none">
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

          {(uploadedImages.length > 0 || uploadedDocuments.length > 0) && (
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 overflow-x-auto">
              <div className="flex shrink-0 gap-2">
                {visibleCombinedAttachments.map((attachment, index) =>
                  attachment.kind === 'image' ? (
                    <div
                      key={index}
                      className="frost-control group ring-frost-border relative flex items-center gap-1 rounded-lg border p-1 ring-1 transition-colors hover:opacity-90"
                    >
                      <img
                        src={attachment.image.base64}
                        alt={attachment.image.file.name}
                        className="h-6 w-6 rounded object-cover"
                      />
                      <div className="flex flex-col">
                        <p className="frost-text max-w-[120px] truncate text-[8px] font-medium">
                          {attachment.image.file.name}
                        </p>
                        <p className="frost-text-subtle text-[8px]">{formatFileSize(attachment.image.file.size)}</p>
                      </div>
                      <button
                        onClick={() => handleRemoveImage(attachment.originalIndex)}
                        className="ml-2 text-red-500 transition-colors hover:text-red-700"
                        title="Remove image"
                      >
                        <X />
                      </button>
                    </div>
                  ) : (
                    <div
                      key={index}
                      className="frost-control group ring-frost-border relative flex items-center gap-2 rounded-lg border p-2 ring-1 transition-colors hover:opacity-90"
                    >
                      <div className="frost-text-muted">📄</div>
                      <div className="flex flex-col">
                        <p className="frost-text max-w-[120px] truncate text-[8px] font-medium">
                          {attachment.document.file.name}
                        </p>
                        <p className="frost-text-subtle text-[8px]">{formatFileSize(attachment.document.file.size)}</p>
                      </div>
                      <button
                        onClick={() => handleRemoveDocument(attachment.originalIndex)}
                        className="ml-2 text-red-500 transition-colors hover:text-red-700"
                        title="Remove document"
                      >
                        <X />
                      </button>
                    </div>
                  )
                )}
                {remainingCombinedAttachmentsCount > 0 && (
                  <Popover>
                    <PopoverTrigger asChild>
                      <button
                        type="button"
                        className="frost-control frost-text-muted ring-frost-border hover:text-frost-text flex cursor-pointer items-center rounded-lg border px-2 text-xs font-medium ring-1 transition-colors"
                        title="Show remaining attachments"
                      >
                        +{remainingCombinedAttachmentsCount}
                      </button>
                    </PopoverTrigger>
                    <PopoverContent align="start" className="frost-glass-strong border-frost-border w-64 p-2">
                      <div className="flex flex-col gap-1.5">
                        {remainingCombinedAttachments.map((attachment, index) => (
                          <p
                            key={`${attachment.kind}-${attachment.originalIndex}-${index}`}
                            className="frost-text truncate text-xs"
                          >
                            {attachment.kind === 'image' ? attachment.image.file.name : attachment.document.file.name}
                          </p>
                        ))}
                      </div>
                    </PopoverContent>
                  </Popover>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="relative flex w-full gap-2">
          <input
            type="file"
            id="imageInput"
            accept={IMAGE_ACCEPT_ATTRIBUTE}
            onChange={handleImageUpload}
            className="hidden"
            disabled={uploadingImage}
            multiple
          />
          <input
            type="file"
            id="documentInput"
            accept={DOCUMENT_ACCEPT_ATTRIBUTE}
            onChange={handleDocumentUpload}
            className="hidden"
            disabled={uploadingDocument}
            multiple
          />
          {showVariablesInput && (
            <div
              ref={variablesModalRef}
              className="frost-card ring-frost-border absolute -top-[332px] left-0 z-20 flex w-96 flex-col gap-4 rounded-xl border p-4 ring-1"
            >
              <div className="flex items-center justify-between">
                <label htmlFor="variables" className="frost-text text-base leading-normal font-normal">
                  Variables (JSON)
                </label>
                <button
                  onClick={() => setShowVariablesInput(false)}
                  className="frost-text-subtle hover:text-frost-text cursor-pointer transition-colors"
                >
                  <X />
                </button>
              </div>
              <Textarea
                id="variables"
                value={inferenceVariables}
                onChange={(e) => setInferenceVariables(e.target.value)}
                rows={5}
                className="font-mono"
                placeholder='{"key": "value"}'
              />
              <p className="frost-text-muted text-sm leading-normal font-normal">
                Define your variables in JSON format. Variables will be passed to the agent during inference.
              </p>
              <Button onClick={() => setShowVariablesInput(false)}>Done</Button>
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
              <SelectTrigger className="frost-text inline-flex cursor-pointer rounded-md border-0 bg-transparent text-sm font-medium whitespace-nowrap shadow-none ring-0 transition-all outline-none focus:ring-0 focus:outline-none focus-visible:ring-0 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&>span]:hidden [&>svg:last-child]:hidden">
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
            <div className="frost-control ring-frost-border flex w-full resize-none items-center justify-between rounded-lg border p-2 text-sm ring-1 outline-none">
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
                className="flex-1 resize-none border-0 bg-transparent shadow-none ring-0 outline-none focus-visible:ring-0"
                placeholder="Ask anything"
              />
              <button
                type="button"
                onClick={handleQuestionEntered}
                className="bg-brand hover:bg-brand-hover h-max w-max rounded-full p-2 text-white"
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
