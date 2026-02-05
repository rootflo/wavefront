import { IApiResponse } from '@app/lib/axios';

// Telephony provider types
export type TelephonyProvider = 'twilio' | 'exotel';

// Connection types
export type ConnectionType = 'websocket' | 'sip';

// SIP transport protocols
export type SipTransport = 'udp' | 'tcp' | 'tls';

// Credentials interface for Twilio
export interface TwilioCredentials {
  account_sid: string;
  auth_token: string;
}

// Credentials interface for Exotel
export interface ExotelCredentials {
  api_key: string;
  api_token: string;
  account_sid: string;
  subdomain: string;
}

// Union type for all provider credentials
export type TelephonyCredentials = TwilioCredentials | ExotelCredentials;

// Webhook configuration (currently not implemented, always null)
export interface WebhookConfig {
  status_callback_url: string;
}

// SIP configuration
export interface SipConfig {
  sip_domain: string;
  port?: number;
  transport?: SipTransport;
}

// Main telephony configuration interface
export interface TelephonyConfig {
  id: string;
  display_name: string;
  description?: string | null;
  provider: TelephonyProvider;
  connection_type: ConnectionType;
  credentials: TelephonyCredentials;
  webhook_config?: WebhookConfig | null;
  sip_config?: SipConfig | null;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

// Request to create a new telephony configuration
export interface CreateTelephonyConfigRequest {
  display_name: string;
  description?: string;
  provider: TelephonyProvider;
  connection_type: ConnectionType;
  credentials: TelephonyCredentials;
  webhook_config?: WebhookConfig | null;
  sip_config?: SipConfig | null;
}

// Request to update an existing telephony configuration (all fields optional)
export interface UpdateTelephonyConfigRequest {
  display_name?: string;
  description?: string | null;
  provider?: TelephonyProvider;
  connection_type?: ConnectionType;
  credentials?: TelephonyCredentials;
  webhook_config?: WebhookConfig | null;
  sip_config?: SipConfig | null;
}

// Response data for create/update/delete operations
export interface TelephonyConfigData {
  message: string;
  telephony_config_id: string;
}

// Response data for list operations
export interface TelephonyConfigListData {
  telephony_configs: TelephonyConfig[];
}

// API response types
export type TelephonyConfigResponse = IApiResponse<TelephonyConfigData>;
export type TelephonyConfigDetailResponse = IApiResponse<TelephonyConfig>;
export type TelephonyConfigListResponse = IApiResponse<TelephonyConfigListData>;
