import { AuthenticatorType } from '@app/types/authenticator';

export type ParameterType = 'string' | 'number' | 'boolean' | 'select' | 'array' | 'object';

export interface ParameterConfig {
  type: ParameterType;
  default: unknown;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  placeholder?: string;
  required?: boolean;
  options?: Array<{ value: string | number; label: string }>;
  pattern?: string;
  fields?: Record<string, ParameterConfig>; // For nested objects
}

export interface ProviderConfig {
  name: string;
  badge: {
    bg: string;
    text: string;
  };
  parameters: Record<string, ParameterConfig>;
}

export const AUTHENTICATOR_PROVIDERS_CONFIG: Record<AuthenticatorType, ProviderConfig> = {
  google_oauth: {
    name: 'Google OAuth 2.0',
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
        description: 'Google OAuth client secret',
        placeholder: 'GOCSPX-abc123def456ghi789jkl',
      },
      redirect_uri: {
        type: 'string',
        default: '',
        required: true,
        description: 'OAuth callback URL (must be registered in Google Cloud Console)',
        placeholder: 'https://yourapp.com/auth/google/callback',
        pattern: '^https?://.+',
      },
      client_redirect_success_url: {
        type: 'string',
        default: '',
        required: true,
        description: 'URL to redirect users after successful authentication',
        placeholder: 'https://yourapp.com/dashboard',
        pattern: '^https?://.+',
      },
      client_redirect_failure_url: {
        type: 'string',
        default: '',
        required: true,
        description: 'URL to redirect users after failed authentication',
        placeholder: 'https://yourapp.com/login?error=auth_failed',
        pattern: '^https?://.+',
      },
      scopes: {
        type: 'array',
        default: ['openid', 'email', 'profile'],
        required: true,
        description: 'OAuth scopes to request (comma-separated)',
        placeholder: 'openid, email, profile',
      },
      hosted_domain: {
        type: 'string',
        default: '',
        required: false,
        description: 'Restrict authentication to a specific Google Workspace domain (optional)',
        placeholder: 'yourcompany.com',
      },
      access_type: {
        type: 'select',
        default: 'offline',
        required: false,
        description: 'Access type for refresh token',
        options: [
          { value: 'offline', label: 'Offline (get refresh token)' },
          { value: 'online', label: 'Online' },
        ],
      },
      prompt: {
        type: 'select',
        default: 'consent',
        required: false,
        description: 'Prompt type',
        options: [
          { value: 'consent', label: 'Consent (always get refresh token)' },
          { value: 'select_account', label: 'Select Account' },
          { value: 'none', label: 'None' },
        ],
      },
    },
  },
  microsoft_oauth: {
    name: 'Microsoft OAuth 2.0',
    badge: {
      bg: 'bg-blue-100',
      text: 'text-blue-800',
    },
    parameters: {
      client_id: {
        type: 'string',
        default: '',
        required: true,
        description: 'Microsoft Application (client) ID from Azure Portal',
        placeholder: '12345678-1234-1234-1234-123456789abc',
      },
      client_secret: {
        type: 'string',
        default: '',
        required: true,
        description: 'Microsoft client secret value',
        placeholder: 'abc~123DEF456-ghi.789JKL',
      },
      tenant_id: {
        type: 'string',
        default: 'common',
        required: true,
        description: 'Azure AD tenant ID or "common" for multi-tenant',
        placeholder: '87654321-4321-4321-4321-cba987654321 or common',
      },
      redirect_uri: {
        type: 'string',
        default: '',
        required: true,
        description: 'OAuth callback URL (must be registered in Azure Portal)',
        placeholder: 'https://yourapp.com/auth/microsoft/callback',
        pattern: '^https?://.+',
      },
      client_redirect_success_url: {
        type: 'string',
        default: '',
        required: true,
        description: 'URL to redirect users after successful authentication',
        placeholder: 'https://yourapp.com/dashboard',
        pattern: '^https?://.+',
      },
      client_redirect_failure_url: {
        type: 'string',
        default: '',
        required: true,
        description: 'URL to redirect users after failed authentication',
        placeholder: 'https://yourapp.com/login?error=auth_failed',
        pattern: '^https?://.+',
      },
      scopes: {
        type: 'array',
        default: ['openid', 'email', 'profile', 'User.Read'],
        required: true,
        description: 'Microsoft Graph API scopes to request (comma-separated)',
        placeholder: 'openid, email, profile, User.Read',
      },
      authority: {
        type: 'string',
        default: 'https://login.microsoftonline.com/',
        required: false,
        description: 'Authority URL',
        pattern: '^https://.+',
      },
      response_type: {
        type: 'string',
        default: 'code',
        required: false,
        description: 'OAuth response type',
      },
      response_mode: {
        type: 'string',
        default: 'query',
        required: false,
        description: 'OAuth response mode',
      },
    },
  },
  email_password: {
    name: 'Email & Password',
    badge: {
      bg: 'bg-green-100',
      text: 'text-green-800',
    },
    parameters: {
      password_policy: {
        type: 'object',
        default: {
          min_length: 8,
          require_uppercase: true,
          require_lowercase: true,
          require_numbers: true,
          require_special_chars: false,
          max_attempts: 5,
          lockout_duration: 900,
        },
        required: true,
        description: 'Password validation and security settings',
        fields: {
          min_length: {
            type: 'number',
            default: 8,
            min: 6,
            max: 128,
            required: true,
            description: 'Minimum password length (at least 6)',
          },
          require_uppercase: {
            type: 'boolean',
            default: true,
            required: true,
            description: 'Require at least one uppercase letter',
          },
          require_lowercase: {
            type: 'boolean',
            default: true,
            required: true,
            description: 'Require at least one lowercase letter',
          },
          require_numbers: {
            type: 'boolean',
            default: true,
            required: true,
            description: 'Require at least one number',
          },
          require_special_chars: {
            type: 'boolean',
            default: false,
            required: true,
            description: 'Require at least one special character',
          },
          max_attempts: {
            type: 'number',
            default: 5,
            min: 1,
            max: 20,
            required: true,
            description: 'Maximum failed login attempts before lockout',
          },
          lockout_duration: {
            type: 'number',
            default: 900,
            min: 60,
            max: 86400,
            step: 60,
            required: true,
            description: 'Lockout duration in seconds (minimum 60)',
          },
        },
      },
      two_factor_enabled: {
        type: 'boolean',
        default: false,
        required: false,
        description: 'Enable two-factor authentication',
      },
      password_reset_enabled: {
        type: 'boolean',
        default: true,
        required: false,
        description: 'Enable password reset functionality',
      },
      session_timeout: {
        type: 'number',
        default: 3600,
        min: 300,
        max: 86400,
        step: 60,
        required: false,
        description: 'Session timeout in seconds (default: 3600 = 1 hour)',
      },
      rate_limit_enabled: {
        type: 'boolean',
        default: true,
        required: false,
        description: 'Enable rate limiting for login attempts',
      },
    },
  },
};

// Helper function to get provider configuration
export function getProviderConfig(authType: AuthenticatorType): ProviderConfig | null {
  return AUTHENTICATOR_PROVIDERS_CONFIG[authType] || null;
}

// Helper function to get provider badge colors
export function getProviderBadge(authType: AuthenticatorType): { bg: string; text: string } {
  const config = AUTHENTICATOR_PROVIDERS_CONFIG[authType];
  return config ? config.badge : { bg: 'bg-gray-100', text: 'text-gray-800' };
}

// Helper function to initialize parameters with defaults
export function initializeParameters(authType: AuthenticatorType): Record<string, unknown> {
  const config = getProviderConfig(authType);
  if (!config) return {};

  const params: Record<string, unknown> = {};
  Object.entries(config.parameters).forEach(([key, paramConfig]) => {
    if (paramConfig.type === 'object' && paramConfig.fields) {
      // Handle nested object parameters
      const nestedParams: Record<string, unknown> = {};
      Object.entries(paramConfig.fields).forEach(([nestedKey, nestedConfig]) => {
        if (nestedConfig.default !== undefined) {
          nestedParams[nestedKey] = nestedConfig.default;
        }
      });
      params[key] = nestedParams;
    } else if (paramConfig.default !== undefined) {
      params[key] = paramConfig.default;
    }
  });
  return params;
}

// Helper function to merge saved parameters with defaults
export function mergeParameters(
  authType: AuthenticatorType,
  savedParams: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  const defaultParams = initializeParameters(authType);
  if (!savedParams) return defaultParams;

  const merged = { ...defaultParams };
  Object.entries(savedParams).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      // For object parameters, merge nested values
      if (typeof value === 'object' && !Array.isArray(value) && typeof merged[key] === 'object') {
        merged[key] = { ...merged[key], ...value };
      } else {
        merged[key] = value;
      }
    }
  });
  return merged;
}

// Helper function to clean parameters (remove empty/undefined values)
export function cleanParameters(params: Record<string, unknown>): Record<string, unknown> {
  const cleaned: Record<string, unknown> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return;

    // Handle arrays (like scopes)
    if (Array.isArray(value)) {
      const filteredArray = value.filter((item) => item !== '' && item !== null && item !== undefined);
      if (filteredArray.length > 0) {
        cleaned[key] = filteredArray;
      }
      return;
    }

    // Handle nested objects
    if (typeof value === 'object') {
      const nestedCleaned = cleanParameters(value);
      if (Object.keys(nestedCleaned).length > 0) {
        cleaned[key] = nestedCleaned;
      }
      return;
    }

    // Handle primitive values
    if (value !== '') {
      cleaned[key] = value;
    }
  });
  return cleaned;
}

// Helper function to get all authenticator types as options
export function getAuthenticatorTypeOptions(): Array<{ value: AuthenticatorType; label: string }> {
  return Object.entries(AUTHENTICATOR_PROVIDERS_CONFIG).map(([value, config]) => ({
    value: value as AuthenticatorType,
    label: config.name,
  }));
}
