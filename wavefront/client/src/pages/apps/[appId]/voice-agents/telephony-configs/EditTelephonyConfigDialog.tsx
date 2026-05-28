/* eslint-disable @typescript-eslint/no-explicit-any */
import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import {
  getConnectionTypeOptions,
  getTelephonyProviderConfig,
  getTelephonyProviderOptions,
  requiresSipConfig,
} from '@app/config/telephony-providers';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import {
  SipTransport,
  TelephonyConfig,
  TelephonyProvider,
  UpdateTelephonyConfigRequest,
} from '@app/types/telephony-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const updateTelephonyConfigSchema = z.object({
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

type UpdateTelephonyConfigInput = z.infer<typeof updateTelephonyConfigSchema>;

interface EditTelephonyConfigDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  config: TelephonyConfig;
  onSuccess?: () => void;
}

const EditTelephonyConfigDialog: React.FC<EditTelephonyConfigDialogProps> = ({
  isOpen,
  onOpenChange,
  config,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [loading, setLoading] = useState(false);

  const form = useForm<UpdateTelephonyConfigInput>({
    resolver: zodResolver(updateTelephonyConfigSchema),
    defaultValues: {
      display_name: config.display_name,
      description: config.description || '',
      provider: config.provider,
      connection_type: config.connection_type,
      account_sid: '',
      auth_token: '',
      api_key: '',
      api_token: '',
      exotel_account_sid: '',
      subdomain: '',
      sip_domain: config.sip_config?.sip_domain || '',
      sip_port: config.sip_config?.port,
      sip_transport: config.sip_config?.transport,
    },
  });

  const watchedProvider = form.watch('provider');
  const watchedConnectionType = form.watch('connection_type');
  const providerChanged = watchedProvider !== config.provider;

  // Initialize form when dialog opens
  useEffect(() => {
    if (isOpen && config) {
      form.reset({
        display_name: config.display_name,
        description: config.description || '',
        provider: config.provider,
        connection_type: config.connection_type,
        account_sid: '',
        auth_token: '',
        api_key: '',
        api_token: '',
        exotel_account_sid: '',
        subdomain: '',
        sip_domain: config.sip_config?.sip_domain || '',
        sip_port: config.sip_config?.port,
        sip_transport: config.sip_config?.transport,
      });
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

  const onSubmit = async (data: UpdateTelephonyConfigInput) => {
    const provider = data.provider as TelephonyProvider;

    // Validate SIP config if required
    if (requiresSipConfig(provider, data.connection_type)) {
      if (!data.sip_domain?.trim()) {
        notifyError('SIP domain is required for SIP connection type');
        return;
      }
    }

    setLoading(true);
    try {
      const updateData: UpdateTelephonyConfigRequest = {
        display_name: data.display_name.trim(),
        description: data.description?.trim() || null,
        provider: provider,
        connection_type: data.connection_type,
      };

      // Handle credentials based on provider
      const providerChanged = provider !== config.provider;

      if (provider === 'twilio') {
        const nextAccountSid = data.account_sid?.trim();
        const nextAuthToken = data.auth_token?.trim();
        if (providerChanged && (!nextAccountSid || !nextAuthToken)) {
          notifyError('Twilio Account SID and Auth Token are required when switching provider');
          setLoading(false);
          return;
        }
        if (providerChanged || nextAccountSid || nextAuthToken) {
          const base = !providerChanged ? (config.credentials as any) : {};
          updateData.credentials = {
            account_sid: nextAccountSid ?? base.account_sid ?? '',
            auth_token: nextAuthToken ?? base.auth_token ?? '',
          };
        }
      } else if (provider === 'exotel') {
        const nextApiKey = data.api_key?.trim();
        const nextApiToken = data.api_token?.trim();
        const nextAccountSid = data.exotel_account_sid?.trim();
        const nextSubdomain = data.subdomain?.trim();
        if (providerChanged && (!nextApiKey || !nextApiToken || !nextAccountSid || !nextSubdomain)) {
          notifyError('All Exotel credentials are required when switching provider');
          setLoading(false);
          return;
        }
        if (providerChanged || nextApiKey || nextApiToken || nextAccountSid || nextSubdomain) {
          const base = !providerChanged ? (config.credentials as any) : {};
          updateData.credentials = {
            api_key: nextApiKey ?? base.api_key ?? '',
            api_token: nextApiToken ?? base.api_token ?? '',
            account_sid: nextAccountSid ?? base.account_sid ?? '',
            subdomain: nextSubdomain ?? base.subdomain ?? '',
          };
        }
      }

      // Add SIP config if required
      if (requiresSipConfig(provider, data.connection_type) && data.sip_domain?.trim()) {
        updateData.sip_config = {
          sip_domain: data.sip_domain.trim(),
          port: data.sip_port,
          transport: data.sip_transport,
        };
      } else if (!requiresSipConfig(provider, data.connection_type)) {
        updateData.sip_config = null;
      }

      await floConsoleService.telephonyConfigService.updateTelephonyConfig(config.id, updateData);
      notifySuccess('Telephony configuration updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update telephony configuration');
    } finally {
      setLoading(false);
    }
  };

  const providerConfig = getTelephonyProviderConfig(watchedProvider as TelephonyProvider);
  const showSipConfig = requiresSipConfig(watchedProvider as TelephonyProvider, watchedConnectionType);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Telephony Configuration</DialogTitle>
          <DialogDescription>Update the telephony provider configuration</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
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
                    <FormDescription>{field.value?.length || 0}/100 characters</FormDescription>
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
                  <FormDescription>{field.value?.length || 0}/500 characters</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-6">
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
              <div className="grid grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="account_sid"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Account SID{' '}
                        {providerChanged ? (
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
                        {providerChanged ? (
                          <span className="text-red-500">*</span>
                        ) : (
                          '(Optional - leave empty to keep existing)'
                        )}
                      </FormLabel>
                      <FormControl>
                        <Input type="password" placeholder="Enter new auth token to update" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}

            {watchedProvider === 'exotel' && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="api_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          API Key{' '}
                          {providerChanged ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="Enter new API key to update" {...field} />
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
                          {providerChanged ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input type="password" placeholder="Enter new API token to update" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="exotel_account_sid"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Account SID{' '}
                          {providerChanged ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="Enter new account SID to update" {...field} />
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
                          {providerChanged ? (
                            <span className="text-red-500">*</span>
                          ) : (
                            '(Optional - leave empty to keep existing)'
                          )}
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="ccm-api.exotel.com or ccm-api.in.exotel.com" {...field} />
                        </FormControl>
                        <FormDescription>
                          Regional API endpoint (Singapore: ccm-api.exotel.com, India: ccm-api.in.exotel.com)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>
            )}

            {showSipConfig && (
              <div className="rounded-lg border border-gray-200 p-4">
                <h3 className="mb-4 font-medium text-gray-900">SIP Configuration</h3>
                <div className="grid grid-cols-2 gap-6">
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
                        <FormDescription>The SIP domain for your provider</FormDescription>
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
                        <FormDescription>SIP port number (default varies by provider)</FormDescription>
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
                      <FormDescription>The transport protocol for SIP communication</FormDescription>
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
                Update Configuration
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditTelephonyConfigDialog;
