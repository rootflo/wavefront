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
import { ConnectionType, SipTransport, TelephonyProvider } from '@app/types/telephony-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const createTelephonyConfigSchema = z.object({
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

type CreateTelephonyConfigInput = z.infer<typeof createTelephonyConfigSchema>;

interface CreateTelephonyConfigDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const CreateTelephonyConfigDialog: React.FC<CreateTelephonyConfigDialogProps> = ({
  isOpen,
  onOpenChange,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [loading, setLoading] = useState(false);

  const form = useForm<CreateTelephonyConfigInput>({
    resolver: zodResolver(createTelephonyConfigSchema),
    defaultValues: {
      display_name: '',
      description: '',
      provider: 'twilio',
      connection_type: 'websocket',
      account_sid: '',
      auth_token: '',
      api_key: '',
      api_token: '',
      exotel_account_sid: '',
      subdomain: '',
      sip_domain: '',
      sip_port: undefined,
      sip_transport: undefined,
    },
  });

  const watchedProvider = form.watch('provider');
  const watchedConnectionType = form.watch('connection_type');

  // Reset SIP config when connection type changes
  useEffect(() => {
    if (watchedConnectionType === 'websocket') {
      form.setValue('sip_domain', '');
      form.setValue('sip_port', undefined);
      form.setValue('sip_transport', undefined);
    }
  }, [watchedConnectionType, form]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        display_name: '',
        description: '',
        provider: 'twilio',
        connection_type: 'websocket',
        account_sid: '',
        auth_token: '',
        api_key: '',
        api_token: '',
        exotel_account_sid: '',
        subdomain: '',
        sip_domain: '',
        sip_port: undefined,
        sip_transport: undefined,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateTelephonyConfigInput) => {
    const provider = data.provider as TelephonyProvider;

    // Validate provider-specific credentials
    if (provider === 'twilio') {
      if (!data.account_sid?.trim()) {
        notifyError('Account SID is required for Twilio');
        return;
      }
      if (!data.auth_token?.trim()) {
        notifyError('Auth Token is required for Twilio');
        return;
      }
    } else if (provider === 'exotel') {
      if (!data.api_key?.trim()) {
        notifyError('API Key is required for Exotel');
        return;
      }
      if (!data.api_token?.trim()) {
        notifyError('API Token is required for Exotel');
        return;
      }
      if (!data.exotel_account_sid?.trim()) {
        notifyError('Account SID is required for Exotel');
        return;
      }
      if (!data.subdomain?.trim()) {
        notifyError('Subdomain is required for Exotel');
        return;
      }
    }

    // Validate SIP config if required
    if (requiresSipConfig(provider, data.connection_type)) {
      if (!data.sip_domain?.trim()) {
        notifyError('SIP domain is required for SIP connection type');
        return;
      }
    }

    setLoading(true);
    try {
      // Build credentials based on provider
      let credentials: any;
      if (provider === 'twilio') {
        credentials = {
          account_sid: data.account_sid!.trim(),
          auth_token: data.auth_token!.trim(),
        };
      } else if (provider === 'exotel') {
        credentials = {
          api_key: data.api_key!.trim(),
          api_token: data.api_token!.trim(),
          account_sid: data.exotel_account_sid!.trim(),
          subdomain: data.subdomain!.trim(),
        };
      }

      const requestData: {
        display_name: string;
        description?: string;
        provider: TelephonyProvider;
        connection_type: ConnectionType;
        credentials: any;
        webhook_config: null;
        sip_config?: { sip_domain: string; port?: number; transport?: SipTransport };
      } = {
        display_name: data.display_name.trim(),
        description: data.description?.trim() || undefined,
        provider: provider,
        connection_type: data.connection_type,
        credentials: credentials,
        webhook_config: null,
      };

      // Add SIP config if required
      if (requiresSipConfig(provider, data.connection_type) && data.sip_domain?.trim()) {
        requestData.sip_config = {
          sip_domain: data.sip_domain.trim(),
          port: data.sip_port,
          transport: data.sip_transport,
        };
      }

      await floConsoleService.telephonyConfigService.createTelephonyConfig(requestData);
      notifySuccess('Telephony configuration created successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create telephony configuration');
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
          <DialogTitle>Create Telephony Configuration</DialogTitle>
          <DialogDescription>Configure a new telephony provider for voice calls</DialogDescription>
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
                        Account SID <span className="text-red-500">*</span>
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
                        Auth Token <span className="text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input type="password" placeholder="Enter your auth token" {...field} />
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
                          API Key <span className="text-red-500">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="Enter your API key" {...field} />
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
                          API Token <span className="text-red-500">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input type="password" placeholder="Enter your API token" {...field} />
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
                          Account SID <span className="text-red-500">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="Enter your account SID" {...field} />
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
                          Subdomain <span className="text-red-500">*</span>
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
                Create Configuration
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTelephonyConfigDialog;
