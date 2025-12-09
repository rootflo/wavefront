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
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import {
  getConnectionTypeOptions,
  getTelephonyProviderConfig,
  getTelephonyProviderOptions,
  isValidE164PhoneNumber,
  requiresSipConfig,
} from '@app/config/telephony-providers';
import { useNotifyStore } from '@app/store';
import { SipTransport } from '@app/types/telephony-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const createTelephonyConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.string().min(1, 'Provider is required'),
  connection_type: z.enum(['websocket', 'sip']),
  account_sid: z.string().min(1, 'Account SID is required'),
  auth_token: z.string().min(1, 'Auth token is required'),
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

  const [phoneNumbers, setPhoneNumbers] = useState<string[]>(['']);
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
        sip_domain: '',
        sip_port: undefined,
        sip_transport: undefined,
      });
      setPhoneNumbers(['']);
    }
  }, [isOpen, form]);

  const handleAddPhoneNumber = () => {
    setPhoneNumbers([...phoneNumbers, '']);
  };

  const handleRemovePhoneNumber = (index: number) => {
    if (phoneNumbers.length === 1) {
      notifyError('At least one phone number is required');
      return;
    }
    setPhoneNumbers(phoneNumbers.filter((_, i) => i !== index));
  };

  const handlePhoneNumberChange = (index: number, value: string) => {
    const newPhoneNumbers = [...phoneNumbers];
    newPhoneNumbers[index] = value;
    setPhoneNumbers(newPhoneNumbers);
  };

  const validatePhoneNumbers = (): boolean => {
    const filledPhoneNumbers = phoneNumbers.filter((p) => p.trim());

    if (filledPhoneNumbers.length === 0) {
      notifyError('At least one phone number is required');
      return false;
    }

    for (const phone of filledPhoneNumbers) {
      if (!isValidE164PhoneNumber(phone.trim())) {
        notifyError(
          `Invalid phone number format: ${phone}. Phone numbers must be in E.164 format (e.g., +14155551234)`
        );
        return false;
      }
    }

    return true;
  };

  const onSubmit = async (data: CreateTelephonyConfigInput) => {
    if (!validatePhoneNumbers()) {
      return;
    }

    // Validate SIP config if required
    if (requiresSipConfig(data.provider as any, data.connection_type)) {
      if (!data.sip_domain?.trim()) {
        notifyError('SIP domain is required for SIP connection type');
        return;
      }
    }

    const filledPhoneNumbers = phoneNumbers.filter((p) => p.trim()).map((p) => p.trim());

    setLoading(true);
    try {
      const requestData: any = {
        display_name: data.display_name.trim(),
        description: data.description?.trim() || undefined,
        provider: data.provider as any,
        connection_type: data.connection_type,
        credentials: {
          account_sid: data.account_sid.trim(),
          auth_token: data.auth_token.trim(),
        },
        phone_numbers: filledPhoneNumbers,
        webhook_config: null,
      };

      // Add SIP config if required
      if (requiresSipConfig(data.provider as any, data.connection_type) && data.sip_domain?.trim()) {
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
    } catch (error: any) {
      notifyError(error?.response?.data?.error?.message || 'Failed to create telephony configuration');
    } finally {
      setLoading(false);
    }
  };

  const providerConfig = getTelephonyProviderConfig(watchedProvider as any);
  const showSipConfig = requiresSipConfig(watchedProvider as any, watchedConnectionType);

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
                        {getConnectionTypeOptions(watchedProvider as any).map((ct) => (
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

            <div className="rounded-lg border border-gray-200 p-4">
              <div className="mb-4 flex items-center justify-between">
                <Label>
                  Phone Numbers <span className="text-red-500">*</span>
                </Label>
                <Button type="button" variant="outline" size="sm" onClick={handleAddPhoneNumber}>
                  + Add Number
                </Button>
              </div>

              <div className="space-y-3">
                {phoneNumbers.map((phone, index) => (
                  <div key={index} className="flex gap-2">
                    <Input
                      type="text"
                      value={phone}
                      onChange={(e) => handlePhoneNumberChange(index, e.target.value)}
                      placeholder="+14155551234"
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => handleRemovePhoneNumber(index)}
                      disabled={phoneNumbers.length === 1}
                    >
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </Button>
                  </div>
                ))}
              </div>

              <p className="text-muted-foreground mt-2 text-[0.8rem]">
                Phone numbers must be in E.164 format (e.g., +14155551234). Include country code with + prefix.
              </p>
            </div>

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
