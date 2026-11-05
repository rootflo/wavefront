import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import {
  getConnectionTypeOptions,
  getDefaultConnectionType,
  getTelephonyProviderConfig,
  getTelephonyProviderOptions,
  isConnectionTypeAllowed,
  requiresSipConfig,
} from '@app/config/telephony-providers';
import { useCreateTelephonyConfig, useUpdateTelephonyConfig } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import {
  ConnectionType,
  CreateTelephonyConfigRequest,
  SipTransport,
  TelephonyConfig,
  TelephonyCredentials,
  TelephonyProvider,
  UpdateTelephonyConfigRequest,
} from '@app/types/telephony-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useRef } from 'react';
import { useParams } from 'react-router';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const telephonyConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.string().min(1, 'Provider is required'),
  connection_type: z.enum(['websocket', 'sip']),
  // Twilio credentials
  account_sid: z.string().optional(),
  auth_token: z.string().optional(),
  // Exotel credentials
  api_key: z.string().optional(),
  api_token: z.string().optional(),
  exotel_account_sid: z.string().optional(),
  subdomain: z.string().optional(),
  // SIP config
  sip_domain: z.string().optional(),
  sip_port: z.number().optional(),
  sip_transport: z.enum(['udp', 'tcp', 'tls']).optional(),
});

type TelephonyConfigInput = z.infer<typeof telephonyConfigSchema>;

const DEFAULT_PROVIDER: TelephonyProvider = 'twilio';

/** Credentials are never returned by the API, so their fields always start empty. */
const toFormValues = (config?: TelephonyConfig): TelephonyConfigInput => ({
  display_name: config?.display_name ?? '',
  description: config?.description || '',
  provider: config?.provider ?? DEFAULT_PROVIDER,
  connection_type: config?.connection_type ?? 'websocket',
  account_sid: '',
  auth_token: '',
  api_key: '',
  api_token: '',
  exotel_account_sid: '',
  subdomain: '',
  sip_domain: config?.sip_config?.sip_domain || '',
  sip_port: config?.sip_config?.port,
  sip_transport: config?.sip_config?.transport,
});

/** Validates and builds the credentials a new config needs; returns an error message when one is missing. */
const buildNewCredentials = (
  provider: TelephonyProvider,
  data: TelephonyConfigInput
): TelephonyCredentials | string => {
  if (provider === 'twilio') {
    if (!data.account_sid?.trim()) return 'Account SID is required for Twilio';
    if (!data.auth_token?.trim()) return 'Auth Token is required for Twilio';
    return { account_sid: data.account_sid.trim(), auth_token: data.auth_token.trim() };
  }
  if (provider === 'exotel') {
    if (!data.api_key?.trim()) return 'API Key is required for Exotel';
    if (!data.api_token?.trim()) return 'API Token is required for Exotel';
    if (!data.exotel_account_sid?.trim()) return 'Account SID is required for Exotel';
    if (!data.subdomain?.trim()) return 'Subdomain is required for Exotel';
    return {
      api_key: data.api_key.trim(),
      api_token: data.api_token.trim(),
      account_sid: data.exotel_account_sid.trim(),
      subdomain: data.subdomain.trim(),
    };
  }
  if (!data.api_key?.trim()) return 'API Key is required for Smartflo';
  return { api_key: data.api_key.trim() };
};

/**
 * Credentials for an update. Fields left empty keep the stored values; switching provider needs a full new
 * set. Returns undefined to leave credentials untouched, or an error message.
 */
const buildUpdatedCredentials = (
  config: TelephonyConfig,
  provider: TelephonyProvider,
  data: TelephonyConfigInput
): TelephonyCredentials | undefined | string => {
  const providerChanged = provider !== config.provider;
  const base = (providerChanged ? {} : config.credentials) as Record<string, string | undefined>;

  if (provider === 'twilio') {
    const nextAccountSid = data.account_sid?.trim();
    const nextAuthToken = data.auth_token?.trim();
    if (providerChanged && (!nextAccountSid || !nextAuthToken)) {
      return 'Twilio Account SID and Auth Token are required when switching provider';
    }
    if (!providerChanged && !nextAccountSid && !nextAuthToken) return undefined;
    return {
      account_sid: nextAccountSid || base.account_sid || '',
      auth_token: nextAuthToken || base.auth_token || '',
    };
  }
  if (provider === 'exotel') {
    const nextApiKey = data.api_key?.trim();
    const nextApiToken = data.api_token?.trim();
    const nextAccountSid = data.exotel_account_sid?.trim();
    const nextSubdomain = data.subdomain?.trim();
    if (providerChanged && (!nextApiKey || !nextApiToken || !nextAccountSid || !nextSubdomain)) {
      return 'All Exotel credentials are required when switching provider';
    }
    if (!providerChanged && !nextApiKey && !nextApiToken && !nextAccountSid && !nextSubdomain) return undefined;
    return {
      api_key: nextApiKey || base.api_key || '',
      api_token: nextApiToken || base.api_token || '',
      account_sid: nextAccountSid || base.account_sid || '',
      subdomain: nextSubdomain || base.subdomain || '',
    };
  }
  const nextApiKey = data.api_key?.trim();
  if (providerChanged && !nextApiKey) return 'API Key is required when switching to Smartflo';
  if (!providerChanged && !nextApiKey) return undefined;
  return { api_key: nextApiKey || base.api_key || '' };
};

interface TelephonyConfigFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** The config to edit; omit to create one. */
  config?: TelephonyConfig;
}

const TelephonyConfigFormDialog: React.FC<TelephonyConfigFormDialogProps> = ({ isOpen, onOpenChange, config }) => {
  const { app } = useParams<{ app: string }>();
  const { notifyError } = useNotifyStore();
  const createConfig = useCreateTelephonyConfig(app);
  const updateConfig = useUpdateTelephonyConfig(app);
  const isEdit = !!config;
  const loading = createConfig.isPending || updateConfig.isPending;

  const form = useForm<TelephonyConfigInput>({
    resolver: zodResolver(telephonyConfigSchema),
    defaultValues: toFormValues(config),
  });

  const watchedProvider = form.watch('provider');
  const watchedConnectionType = form.watch('connection_type');
  // A new config, or an existing one switched to another provider, needs a full set of credentials
  const credentialsRequired = !config || watchedProvider !== config.provider;
  const previousProviderRef = useRef<string>(config?.provider ?? DEFAULT_PROVIDER);

  // Start from the config being edited, or a blank form, each time the dialog opens
  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(config));
      previousProviderRef.current = config?.provider ?? DEFAULT_PROVIDER;
    }
  }, [isOpen, config, form]);

  // Reset SIP config when connection type changes
  useEffect(() => {
    if (watchedConnectionType === 'websocket') {
      form.setValue('sip_domain', '');
      form.setValue('sip_port', undefined);
      form.setValue('sip_transport', undefined);
    }
  }, [watchedConnectionType, form]);

  // Normalize connection_type and clear credentials when provider changes
  useEffect(() => {
    const provider = watchedProvider as TelephonyProvider;
    if (!provider || !getTelephonyProviderConfig(provider)) {
      return;
    }
    const current = form.getValues('connection_type') as ConnectionType;
    if (!isConnectionTypeAllowed(provider, current)) {
      form.setValue('connection_type', getDefaultConnectionType(provider));
    }

    if (previousProviderRef.current !== provider) {
      previousProviderRef.current = provider;
      form.setValue('account_sid', '');
      form.setValue('auth_token', '');
      form.setValue('api_key', '');
      form.setValue('api_token', '');
      form.setValue('exotel_account_sid', '');
      form.setValue('subdomain', '');
    }
  }, [watchedProvider, form]);

  const onSubmit = (data: TelephonyConfigInput) => {
    const provider = data.provider as TelephonyProvider;
    const providerConfig = getTelephonyProviderConfig(provider);

    // Reject connection types not allowed for the provider (Smartflo is websocket-only)
    if (!isConnectionTypeAllowed(provider, data.connection_type)) {
      notifyError(`${providerConfig.name} only supports: ${providerConfig.allowedConnectionTypes.join(', ')}`);
      return;
    }

    // Validate SIP config if required
    const needsSip = requiresSipConfig(provider, data.connection_type);
    if (needsSip && !data.sip_domain?.trim()) {
      notifyError('SIP domain is required for SIP connection type');
      return;
    }
    const sipConfig =
      needsSip && data.sip_domain?.trim()
        ? { sip_domain: data.sip_domain.trim(), port: data.sip_port, transport: data.sip_transport }
        : undefined;
    const close = () => onOpenChange(false);

    if (!config) {
      const credentials = buildNewCredentials(provider, data);
      if (typeof credentials === 'string') {
        notifyError(credentials);
        return;
      }
      const requestData: CreateTelephonyConfigRequest = {
        display_name: data.display_name.trim(),
        description: data.description?.trim() || undefined,
        provider,
        connection_type: data.connection_type,
        credentials,
        webhook_config: null,
        sip_config: sipConfig,
      };
      createConfig.mutate(requestData, { onSuccess: close });
      return;
    }

    const credentials = buildUpdatedCredentials(config, provider, data);
    if (typeof credentials === 'string') {
      notifyError(credentials);
      return;
    }
    const updateData: UpdateTelephonyConfigRequest = {
      display_name: data.display_name.trim(),
      description: data.description?.trim() || null,
      provider,
      connection_type: data.connection_type,
    };
    if (credentials) updateData.credentials = credentials;
    // Clear stored SIP settings once the connection no longer uses SIP
    if (sipConfig) updateData.sip_config = sipConfig;
    else if (!needsSip) updateData.sip_config = null;
    updateConfig.mutate({ configId: config.id, data: updateData }, { onSuccess: close });
  };

  const providerConfig = getTelephonyProviderConfig(watchedProvider as TelephonyProvider);
  const showSipConfig = requiresSipConfig(watchedProvider as TelephonyProvider, watchedConnectionType);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Telephony Configuration' : 'Create Telephony Configuration'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Update the telephony provider configuration'
              : 'Configure a new telephony provider for voice calls'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="display_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Display Name <span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Twilio US Production" maxLength={100} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Provider <span className="text-red-500">*</span>
                    </FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {getTelephonyProviderOptions().map((p) => (
                          <SelectItem key={p.value} value={p.value}>
                            {p.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem className="col-span-2">
                  <FormLabel>Description (Optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Describe the purpose or use case for this telephony configuration"
                      maxLength={500}
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="connection_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Connection Type <span className="text-red-500">*</span>
                    </FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select connection type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {getConnectionTypeOptions(watchedProvider as TelephonyProvider).map((ct) => (
                          <SelectItem key={ct.value} value={ct.value}>
                            {ct.label} - {ct.description}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Provider-specific credential fields */}
            {watchedProvider === 'twilio' && (
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="account_sid"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Account SID{' '}
                        {credentialsRequired ? (
                          <span className="text-red-500">*</span>
                        ) : (
                          '(Optional - leave empty to keep existing)'
                        )}
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="auth_token"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Auth Token{' '}
                        {credentialsRequired ? (
                          <span className="text-red-500">*</span>
                        ) : (
                          '(Optional - leave empty to keep existing)'
                        )}
                      </FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          placeholder={credentialsRequired ? 'Enter your auth token' : 'Enter new auth token to update'}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}

            {watchedProvider === 'exotel' && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="api_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          API Key{' '}
                          {credentialsRequired ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input
                            placeholder={credentialsRequired ? 'Enter your API key' : 'Enter new API key to update'}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="api_token"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          API Token{' '}
                          {credentialsRequired ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder={credentialsRequired ? 'Enter your API token' : 'Enter new API token to update'}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="exotel_account_sid"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Account SID{' '}
                          {credentialsRequired ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input
                            placeholder={
                              credentialsRequired ? 'Enter your account SID' : 'Enter new account SID to update'
                            }
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="subdomain"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Subdomain{' '}
                          {credentialsRequired ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="ccm-api.exotel.com or ccm-api.in.exotel.com" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>
            )}

            {watchedProvider === 'smartflo' && (
              <FormField
                control={form.control}
                name="api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      API Key{' '}
                      {credentialsRequired ? (
                        <span className="text-red-500">*</span>
                      ) : (
                        '(Optional - leave empty to keep existing)'
                      )}
                    </FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder={
                          credentialsRequired ? 'Enter your Smartflo API key' : 'Enter new Smartflo API key to update'
                        }
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {showSipConfig && (
              <div className="frost-glass border-frost-border ring-frost-border rounded-lg border p-4 ring-1">
                <h3 className="frost-text mb-4 font-medium">SIP Configuration</h3>
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="sip_domain"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          SIP Domain <span className="text-red-500">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="pstn.twilio.com" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="sip_port"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Port (Optional)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="5060"
                            min={1}
                            max={65535}
                            value={field.value ?? ''}
                            onChange={(e) => field.onChange(e.target.value ? parseInt(e.target.value) : undefined)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="sip_transport"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Transport Protocol (Optional)</FormLabel>
                      <Select
                        onValueChange={(val) => field.onChange(val as SipTransport | undefined)}
                        value={field.value || ''}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select transport..." />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {providerConfig.sipFields.transport.options?.map((opt) => (
                            <SelectItem key={opt.value} value={String(opt.value)}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" loading={loading}>
                {isEdit ? 'Update Configuration' : 'Create Configuration'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default TelephonyConfigFormDialog;
