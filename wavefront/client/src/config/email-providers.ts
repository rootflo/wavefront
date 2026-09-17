import { ParameterConfig, ProviderConfig } from '@app/config/authenticators';
import { EmailCapability, EmailConnectionStatus, EmailProviderType } from '@app/types/email';

// Mirrors the `GmailAppConfig` and `OutlookAppConfig` dataclasses in
// server/plugins/mailer — OAuth credentials only. Gmail Pub/Sub watch settings
// live in triggers runtime config, not on the OAuth app.
export const EMAIL_PROVIDERS_CONFIG: Record<EmailProviderType, ProviderConfig> = {
  gmail: {
    name: 'Gmail',
    badge: {
      bg: 'bg-red-100',
      text: 'text-red-800',
    },
    parameters: {
      client_id: {
        type: 'string',
        default: '',
        required: true,
        description: 'Google OAuth client ID from Google Cloud Console',
        placeholder: '123456789-abcdefghijklmnop.apps.googleusercontent.com',
      },
      client_secret: {
        type: 'string',
        default: '',
        required: true,
        description: 'Google OAuth client secret. Stored encrypted and never returned.',
        placeholder: 'GOCSPX-abc123def456ghi789jkl',
      },
      redirect_uri: {
        type: 'string',
        default: '',
        required: true,
        description: 'Must point at /floware/v1/email-connections/oauth/callback and be registered with Google',
        placeholder: 'https://yourapp.com/floware/v1/email-connections/oauth/callback',
        pattern: '^https?://.+',
      },
    },
  },
  outlook: {
    name: 'Outlook',
    badge: {
      bg: 'bg-blue-100',
      text: 'text-blue-800',
    },
    parameters: {
      client_id: {
        type: 'string',
        default: '',
        required: true,
        description: 'Application (client) ID of the Microsoft Entra app registration',
        placeholder: '00000000-0000-0000-0000-000000000000',
      },
      client_secret: {
        type: 'string',
        default: '',
        required: true,
        description: 'Entra client secret. Stored encrypted and never returned.',
        placeholder: 'abc123~def456ghi789',
      },
      redirect_uri: {
        type: 'string',
        default: '',
        required: true,
        description: 'Must point at /floware/v1/email-connections/oauth/callback and be registered with Entra',
        placeholder: 'https://yourapp.com/floware/v1/email-connections/oauth/callback',
        pattern: '^https?://.+',
      },
      tenant_id: {
        type: 'string',
        default: 'common',
        description: "Directory (tenant) ID. Leave as 'common' for multi-tenant and personal accounts.",
        placeholder: 'common',
      },
      authority_host: {
        type: 'string',
        default: '',
        description: 'Override only for sovereign clouds',
        placeholder: 'https://login.microsoftonline.com',
      },
    },
  },
};

export const EMAIL_CAPABILITIES: Array<{ value: EmailCapability; label: string; description: string }> = [
  { value: 'read', label: 'Read', description: 'Read messages and watch the inbox for triggers' },
  { value: 'send', label: 'Send', description: 'Send mail as this mailbox' },
  { value: 'modify', label: 'Modify', description: 'Change labels and mark messages read' },
];

const STATUS_BADGES: Record<EmailConnectionStatus, { label: string; bg: string; text: string }> = {
  active: { label: 'Active', bg: 'bg-green-50', text: 'text-green-700' },
  pending_auth: { label: 'Awaiting consent', bg: 'bg-amber-50', text: 'text-amber-700' },
  error: { label: 'Error', bg: 'bg-red-50', text: 'text-red-700' },
  revoked: { label: 'Revoked', bg: 'bg-gray-50', text: 'text-gray-500' },
  deleted: { label: 'Deleted', bg: 'bg-gray-50', text: 'text-gray-400' },
};

export function getEmailProviderConfig(provider: EmailProviderType): ProviderConfig | null {
  return EMAIL_PROVIDERS_CONFIG[provider] || null;
}

export function getEmailProviderBadge(provider: EmailProviderType): { bg: string; text: string } {
  const config = EMAIL_PROVIDERS_CONFIG[provider];
  return config ? config.badge : { bg: 'bg-gray-100', text: 'text-gray-800' };
}

export function getEmailProviderOptions(): Array<{ value: EmailProviderType; label: string }> {
  return Object.entries(EMAIL_PROVIDERS_CONFIG).map(([value, config]) => ({
    value: value as EmailProviderType,
    label: config.name,
  }));
}

export function getConnectionStatusBadge(status: EmailConnectionStatus): { label: string; bg: string; text: string } {
  return STATUS_BADGES[status] || { label: status, bg: 'bg-gray-50', text: 'text-gray-700' };
}

/** Config defaults for a provider, as the create form's starting state. */
export function initializeEmailProviderParameters(provider: EmailProviderType): Record<string, unknown> {
  const config = getEmailProviderConfig(provider);
  if (!config) return {};

  const params: Record<string, unknown> = {};
  Object.entries(config.parameters).forEach(([key, paramConfig]: [string, ParameterConfig]) => {
    if (paramConfig.default !== undefined) {
      params[key] = paramConfig.default;
    }
  });
  return params;
}

/** Names of required config fields left blank, for a message the admin can act on. */
export function missingEmailProviderFields(provider: EmailProviderType, params: Record<string, unknown>): string[] {
  const config = getEmailProviderConfig(provider);
  if (!config) return [];

  return Object.entries(config.parameters)
    .filter(([key, paramConfig]) => {
      if (!paramConfig.required) return false;
      const value = params[key];
      return value === undefined || value === null || String(value).trim() === '';
    })
    .map(([key]) => key);
}

/** Drop blanks so an optional field the admin never filled in is absent rather
 *  than an empty string the server would have to interpret. */
export function cleanEmailProviderParameters(params: Record<string, unknown>): Record<string, unknown> {
  const cleaned: Record<string, unknown> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (typeof value === 'string' && value.trim() === '') return;
    cleaned[key] = typeof value === 'string' ? value.trim() : value;
  });
  return cleaned;
}
