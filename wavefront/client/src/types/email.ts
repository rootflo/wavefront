import { IApiResponse } from '@app/lib/axios';

export type EmailProviderType = 'gmail' | 'outlook';

export type EmailCapability = 'read' | 'send' | 'modify';

export type EmailConnectionStatus = 'pending_auth' | 'active' | 'error' | 'revoked' | 'deleted';

// One connected mailbox. Tokens never leave the server; `granted_scopes` is what
// consent actually returned.
export interface EmailConnection {
  id: string;
  name: string;
  provider: EmailProviderType;
  oauth_app_id: string;
  mailbox_email: string;
  status: EmailConnectionStatus;
  granted_scopes: string | null;
  token_expires_at: string | null;
  is_primary: boolean;
  last_error: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateEmailConnectionRequest {
  name: string;
  provider: EmailProviderType;
  oauth_app_id: string;
  capabilities: EmailCapability[];
  success_redirect_url?: string;
  failure_redirect_url?: string;
}

export interface AuthorizeEmailConnectionRequest {
  capabilities: EmailCapability[];
  success_redirect_url?: string;
  failure_redirect_url?: string;
}

export interface SendEmailRequest {
  to: string[];
  subject: string;
  body: string;
  sender_display_name?: string;
}

// Creating a connection returns the consent URL to send the admin to.
export interface EmailConnectionData {
  message: string;
  connection: EmailConnection;
  authorization_url: string;
}

export interface EmailConnectionDetailData {
  connection: EmailConnection;
}

export interface EmailConnectionListData {
  connections: EmailConnection[];
}

export interface EmailConnectionAuthorizeData {
  authorization_url: string;
}

export interface EmailConnectionPrimaryData {
  message: string;
  connection: EmailConnection;
}

export interface EmailConnectionMessageData {
  message: string;
}

export type EmailConnectionResponse = IApiResponse<EmailConnectionData>;
export type EmailConnectionDetailResponse = IApiResponse<EmailConnectionDetailData>;
export type EmailConnectionListResponse = IApiResponse<EmailConnectionListData>;
export type EmailConnectionAuthorizeResponse = IApiResponse<EmailConnectionAuthorizeData>;
export type EmailConnectionPrimaryResponse = IApiResponse<EmailConnectionPrimaryData>;
export type EmailConnectionMessageResponse = IApiResponse<EmailConnectionMessageData>;
