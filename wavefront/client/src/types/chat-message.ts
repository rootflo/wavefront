// Types for chat message content
export interface ImageContent {
  image_base64: string;
  mime_type?: string;
}

export interface DocumentContent {
  document_type: string;
  document_base64?: string;
  mime_type?: string;
  metadata?: {
    filename?: string;
    size?: number;
  };
}

export type ChatMessageContent = string | ImageContent | DocumentContent | Record<string, unknown>;

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: ChatMessageContent;
}
