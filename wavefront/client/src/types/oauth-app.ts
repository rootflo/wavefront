import { IApiResponse } from '@app/lib/axios';
import { EmailProviderType } from '@app/types/email';

// Platform OAuth client credentials. `config` comes back without the client
// secret, which the API only reports as present or not.
export interface OAuthApp {
  id: string;
  name: string;
  description: string | null;
  provider: EmailProviderType;
  is_enabled: boolean;
  has_client_secret: boolean;
  config?: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateOAuthAppRequest {
  name: string;
  provider: EmailProviderType;
  config: Record<string, unknown>;
  description?: string | null;
}

// Omitting `config.client_secret` on update keeps the stored secret.
export interface UpdateOAuthAppRequest {
  name?: string;
  config?: Record<string, unknown>;
  description?: string | null;
}

export interface OAuthAppData {
  message: string;
  app: OAuthApp;
}

export interface OAuthAppDetailData {
  app: OAuthApp;
}

export interface OAuthAppListData {
  apps: OAuthApp[];
}

export interface OAuthAppMessageData {
  message: string;
}

export type OAuthAppResponse = IApiResponse<OAuthAppData>;
export type OAuthAppDetailResponse = IApiResponse<OAuthAppDetailData>;
export type OAuthAppListResponse = IApiResponse<OAuthAppListData>;
export type OAuthAppMessageResponse = IApiResponse<OAuthAppMessageData>;
