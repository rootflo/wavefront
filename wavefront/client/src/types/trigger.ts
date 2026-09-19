import { IApiResponse } from '@app/lib/axios';

export type TriggerProvider = 'gmail';

export type TriggerEntityType = 'agent' | 'workflow';

export type TriggerStatus = 'pending_auth' | 'active' | 'paused' | 'error' | 'deleted';

export interface TriggerFilterConfig {
  subject_regex?: string | null;
  allowed_mime_types?: string[] | null;
}

export interface Trigger {
  id: string;
  name: string;
  provider: TriggerProvider;
  entity_type: TriggerEntityType;
  entity_id: string;
  namespace: string | null;
  status: TriggerStatus;
  filter_config: TriggerFilterConfig | Record<string, unknown> | null;
  provider_config: Record<string, unknown> | null;
  connection_id: string;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateTriggerRequest {
  name: string;
  provider: TriggerProvider;
  entity_type: TriggerEntityType;
  entity_id: string;
  connection_id: string;
  namespace?: string | null;
  filter_config?: TriggerFilterConfig;
}

export interface CreateTriggerResult {
  trigger_id: string;
  status: TriggerStatus;
  mailbox_email: string | null;
}

export interface CreateTriggerResponseData {
  message: string;
  data: CreateTriggerResult;
}

export interface TriggerResponseData {
  data: Trigger;
}

export interface TriggerListResponseData {
  data: Trigger[];
}

export type CreateTriggerResponse = IApiResponse<CreateTriggerResponseData>;
export type TriggerDetailResponse = IApiResponse<TriggerResponseData>;
export type ListTriggersResponse = IApiResponse<TriggerListResponseData>;
