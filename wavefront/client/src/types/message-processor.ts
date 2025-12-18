import { IApiResponse } from '@app/lib/axios';

export interface MessageProcessor {
  id: string;
  name: string;
  description?: string;
  yaml_content?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MessageProcessorListItem {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MessageProcessorData {
  message?: string;
  processor_id?: string;
  processor?: MessageProcessor;
  processors?: MessageProcessorListItem[];
}

export interface MessageProcessorListData {
  processors: MessageProcessorListItem[];
}

export interface CreateMessageProcessorRequest {
  name: string;
  yaml_content: string;
  description?: string;
}

export interface UpdateMessageProcessorRequest {
  name?: string;
  description?: string;
  yaml_content?: string;
}

export interface ExecuteMessageProcessorRequest {
  input_data: Record<string, unknown>;
  execution_context?: Record<string, unknown>;
}

export interface ExecuteMessageProcessorData {
  result: unknown;
}

export type MessageProcessorResponse = IApiResponse<MessageProcessorData>;
export type MessageProcessorListResponse = IApiResponse<MessageProcessorListData>;
export type ExecuteMessageProcessorResponse = IApiResponse<ExecuteMessageProcessorData>;
