import { IApiResponse } from '@app/lib/axios';

// Authenticator type union matching API auth_type field
export type AuthenticatorType = 'google_oauth' | 'microsoft_oauth' | 'email_password';

// Main Authenticator entity interface
export interface Authenticator {
  auth_id: string;
  auth_name: string;
  auth_type: AuthenticatorType;
  auth_desc: string | null;
  config: Record<string, any> | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

// Create request interface
export interface CreateAuthenticatorRequest {
  auth_name: string;
  auth_type: AuthenticatorType;
  auth_desc?: string | null;
  config: Record<string, any>;
}

// Update request interface (all fields optional except config)
export interface UpdateAuthenticatorRequest {
  auth_desc?: string | null;
  config: Record<string, any>;
}

// Response data interfaces
export interface AuthenticatorData {
  message: string;
  authenticator: Authenticator;
}

export interface AuthenticatorListData {
  authenticators: Authenticator[];
}

export interface AuthenticatorEnableDisableData {
  message: string;
}

// Response type aliases using IApiResponse wrapper
export type AuthenticatorResponse = IApiResponse<AuthenticatorData>;
export type AuthenticatorDetailResponse = IApiResponse<Authenticator>;
export type AuthenticatorListResponse = IApiResponse<AuthenticatorListData>;
export type AuthenticatorEnableDisableResponse = IApiResponse<AuthenticatorEnableDisableData>;

// Google OAuth specific config interface
export interface GoogleOAuthConfig {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
  client_redirect_success_url: string;
  client_redirect_failure_url: string;
  scopes: string[];
  hosted_domain?: string;
  access_type?: string;
  prompt?: string;
}

// Microsoft OAuth specific config interface
export interface MicrosoftOAuthConfig {
  client_id: string;
  client_secret: string;
  tenant_id: string;
  redirect_uri: string;
  client_redirect_success_url: string;
  client_redirect_failure_url: string;
  scopes: string[];
  authority?: string;
  response_type?: string;
  response_mode?: string;
}

// Email/Password specific config interface
export interface EmailPasswordConfig {
  password_policy: {
    min_length: number;
    require_uppercase: boolean;
    require_lowercase: boolean;
    require_numbers: boolean;
    require_special_chars: boolean;
    max_attempts: number;
    lockout_duration: number;
  };
  two_factor_enabled?: boolean;
  password_reset_enabled?: boolean;
  session_timeout?: number;
  rate_limit_enabled?: boolean;
}
