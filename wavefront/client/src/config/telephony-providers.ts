import { TelephonyProvider, ConnectionType } from '@app/types/telephony-config';

// Field type definitions for dynamic form rendering
export type FieldType = 'string' | 'number' | 'boolean' | 'select' | 'array';

export interface FieldConfig {
  type: FieldType;
  label: string;
  required?: boolean;
  options?: Array<{ value: string | number; label: string }>;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  helpText?: string;
}

// SIP configuration fields
export interface SipFieldsConfig {
  sip_domain: FieldConfig;
  port: FieldConfig;
  transport: FieldConfig;
}

// Connection type configuration
export interface ConnectionTypeConfig {
  label: string;
  description: string;
  requiresSipConfig: boolean;
}

// Provider configuration
export interface TelephonyProviderConfig {
  name: string;
  badge: {
    bg: string;
    text: string;
  };
  allowedConnectionTypes: ConnectionType[]; // List of allowed connection types
  connectionTypes: {
    websocket: ConnectionTypeConfig;
    sip: ConnectionTypeConfig;
  };
  sipFields: SipFieldsConfig;
}

// Configuration for all telephony providers
export const TELEPHONY_PROVIDERS_CONFIG: Record<TelephonyProvider, TelephonyProviderConfig> = {
  twilio: {
    name: 'Twilio',
    badge: {
      bg: 'bg-red-100',
      text: 'text-red-800',
    },
    allowedConnectionTypes: ['websocket'], // Currently only websocket is allowed, add 'sip' when ready
    connectionTypes: {
      websocket: {
        label: 'WebSocket',
        description: 'Real-time bidirectional audio streaming',
        requiresSipConfig: false,
      },
      sip: {
        label: 'SIP',
        description: 'Session Initiation Protocol for PBX integration',
        requiresSipConfig: true,
      },
    },
    sipFields: {
      sip_domain: {
        type: 'string',
        label: 'SIP Domain',
        required: true,
        placeholder: 'e.g., pstn.twilio.com',
        helpText: 'The SIP domain for your Twilio configuration',
      },
      port: {
        type: 'number',
        label: 'Port',
        required: false,
        min: 1,
        max: 65535,
        placeholder: '5060',
        helpText: 'SIP port number (default varies by provider)',
      },
      transport: {
        type: 'select',
        label: 'Transport Protocol',
        required: false,
        options: [
          { value: 'udp', label: 'UDP - User Datagram Protocol (fastest)' },
          { value: 'tcp', label: 'TCP - Transmission Control Protocol (reliable)' },
          { value: 'tls', label: 'TLS - Transport Layer Security (encrypted)' },
        ],
        helpText: 'The transport protocol for SIP communication',
      },
    },
  },
};

// Connection type badge colors
export const CONNECTION_TYPE_BADGES: Record<ConnectionType, { bg: string; text: string }> = {
  websocket: {
    bg: 'bg-blue-100',
    text: 'text-blue-800',
  },
  sip: {
    bg: 'bg-purple-100',
    text: 'text-purple-800',
  },
};

// Helper functions

/**
 * Get provider configuration
 */
export const getTelephonyProviderConfig = (provider: TelephonyProvider): TelephonyProviderConfig => {
  return TELEPHONY_PROVIDERS_CONFIG[provider];
};

/**
 * Get provider badge classes
 */
export const getTelephonyProviderBadge = (provider: TelephonyProvider): { bg: string; text: string } => {
  return TELEPHONY_PROVIDERS_CONFIG[provider].badge;
};

/**
 * Get connection type badge classes
 */
export const getConnectionTypeBadge = (connectionType: ConnectionType): { bg: string; text: string } => {
  return CONNECTION_TYPE_BADGES[connectionType];
};

/**
 * Check if SIP config is required for the selected connection type
 */
export const requiresSipConfig = (provider: TelephonyProvider, connectionType: ConnectionType): boolean => {
  return TELEPHONY_PROVIDERS_CONFIG[provider].connectionTypes[connectionType].requiresSipConfig;
};

/**
 * Get all available providers as options for dropdowns
 */
export const getTelephonyProviderOptions = (): Array<{ value: TelephonyProvider; label: string }> => {
  return Object.entries(TELEPHONY_PROVIDERS_CONFIG).map(([value, config]) => ({
    value: value as TelephonyProvider,
    label: config.name,
  }));
};

/**
 * Get connection type options for a provider (filtered by allowed types)
 */
export const getConnectionTypeOptions = (
  provider: TelephonyProvider
): Array<{ value: ConnectionType; label: string; description: string }> => {
  const config = TELEPHONY_PROVIDERS_CONFIG[provider];
  return config.allowedConnectionTypes.map((connectionType) => {
    const typeConfig = config.connectionTypes[connectionType];
    return {
      value: connectionType,
      label: typeConfig.label,
      description: typeConfig.description,
    };
  });
};

/**
 * Initialize default SIP config values
 */
export const getDefaultSipConfig = () => ({
  sip_domain: '',
  port: undefined,
  transport: undefined,
});

/**
 * Validate E.164 phone number format
 */
export const isValidE164PhoneNumber = (phoneNumber: string): boolean => {
  // E.164 format: +[country code][number] (max 15 digits total)
  const e164Regex = /^\+[1-9]\d{1,14}$/;
  return e164Regex.test(phoneNumber);
};

/**
 * Format phone number for display
 */
export const formatPhoneNumber = (phoneNumber: string): string => {
  // Simple formatting for display - can be enhanced later
  return phoneNumber;
};
