import floConsoleService from '@app/api';
import { Alert, AlertDescription } from '@app/components/ui/alert';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
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
import { Slider } from '@app/components/ui/slider';
import { Textarea } from '@app/components/ui/textarea';
import { VOICE_PROVIDERS_CONFIG, getProviderConfig, initializeParameters } from '@app/config/voice-providers';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const createSttConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.string().min(1, 'Provider is required'),
  api_key: z.string().min(1, 'API key is required'),
  language: z.string().optional(),
});

type CreateSttConfigInput = z.infer<typeof createSttConfigSchema>;

interface CreateSttConfigDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const CreateSttConfigDialog: React.FC<CreateSttConfigDialogProps> = ({ isOpen, onOpenChange, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [parameters, setParameters] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);

  const form = useForm<CreateSttConfigInput>({
    resolver: zodResolver(createSttConfigSchema),
    defaultValues: {
      display_name: '',
      description: '',
      provider: 'deepgram',
      api_key: '',
      language: '',
    },
  });

  const watchedProvider = form.watch('provider');

  // Reset parameters when provider changes
  useEffect(() => {
    if (isOpen && watchedProvider) {
      setParameters(initializeParameters('stt', watchedProvider));
    }
  }, [watchedProvider, isOpen]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        display_name: '',
        description: '',
        provider: 'deepgram',
        api_key: '',
        language: '',
      });
      setParameters({});
    }
  }, [isOpen, form]);

  const setParameter = (key: string, value: any) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const buildParameters = () => {
    const config = getProviderConfig('stt', watchedProvider);
    if (!config) return null;

    const params: Record<string, any> = {};

    Object.entries(parameters).forEach(([key, value]) => {
      const paramConfig = config.parameters[key];
      if (!paramConfig) return;

      if (value !== '' && value !== undefined) {
        params[key] = value;
      }
    });

    return Object.keys(params).length > 0 ? params : null;
  };

  const onSubmit = async (data: CreateSttConfigInput) => {
    setLoading(true);
    try {
      await floConsoleService.sttConfigService.createSttConfig({
        display_name: data.display_name.trim(),
        description: data.description?.trim() || null,
        provider: data.provider as any,
        api_key: data.api_key.trim(),
        language: data.language?.trim() || null,
        parameters: buildParameters(),
      });
      notifySuccess('STT configuration created successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error: any) {
      notifyError(error?.response?.data?.error?.message || 'Failed to create STT configuration');
    } finally {
      setLoading(false);
    }
  };

  const renderParameterField = (key: string) => {
    const config = getProviderConfig('stt', watchedProvider);
    if (!config) return null;

    const paramConfig = config.parameters[key];
    if (!paramConfig) return null;

    const value = parameters[key];

    switch (paramConfig.type) {
      case 'boolean':
        return (
          <div key={key} className="col-span-2">
            <div className="flex items-center space-x-2">
              <Checkbox id={key} checked={value || false} onCheckedChange={(checked) => setParameter(key, checked)} />
              <Label htmlFor={key} className="cursor-pointer">
                {paramConfig.description || key}
              </Label>
            </div>
          </div>
        );

      case 'number':
        if (paramConfig.options && paramConfig.options.length > 0) {
          return (
            <div key={key} className="space-y-2">
              <Label>{paramConfig.description || key}</Label>
              <Select
                value={
                  value !== undefined && value !== null
                    ? String(value)
                    : paramConfig.default !== undefined
                      ? String(paramConfig.default)
                      : ''
                }
                onValueChange={(val) => setParameter(key, val ? parseInt(val) : undefined)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {paramConfig.options.map((option) => (
                    <SelectItem key={option} value={String(option)}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        }

        if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
          return (
            <div key={key} className="col-span-2 space-y-2">
              <Label>
                {paramConfig.description || key}: {value ?? paramConfig.default}
              </Label>
              <Slider
                min={paramConfig.min}
                max={paramConfig.max}
                step={paramConfig.step || 1}
                value={[value ?? paramConfig.default]}
                onValueChange={(values: number[]) => setParameter(key, values[0])}
              />
              {paramConfig.description && (
                <p className="text-muted-foreground text-[0.8rem]">{paramConfig.description}</p>
              )}
            </div>
          );
        }

        return (
          <div key={key} className="space-y-2">
            <Label>{paramConfig.description || key}</Label>
            <Input
              type="number"
              value={value ?? ''}
              onChange={(e) => setParameter(key, e.target.value ? parseInt(e.target.value) : undefined)}
              placeholder={paramConfig.placeholder}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">e.g., {paramConfig.placeholder}</p>
            )}
          </div>
        );

      case 'string':
      default:
        if (key === 'language') return null;

        if (paramConfig.options && paramConfig.options.length > 0) {
          return (
            <div key={key} className="space-y-2">
              <Label>{paramConfig.description || key}</Label>
              <Select value={value || paramConfig.default || ''} onValueChange={(val) => setParameter(key, val)}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {paramConfig.options.map((option) => (
                    <SelectItem key={String(option)} value={String(option)}>
                      {String(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        }

        return (
          <div key={key} className="space-y-2">
            <Label>{paramConfig.description || key}</Label>
            <Input
              type="text"
              value={value || ''}
              onChange={(e) => setParameter(key, e.target.value)}
              placeholder={paramConfig.placeholder}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">Default: {paramConfig.placeholder}</p>
            )}
          </div>
        );
    }
  };

  const providerConfig = getProviderConfig('stt', watchedProvider);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create STT Configuration</DialogTitle>
          <DialogDescription>Configure a new Speech-to-Text provider</DialogDescription>
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
                      <Input placeholder="e.g., Deepgram English Transcription" maxLength={100} {...field} />
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
                        {VOICE_PROVIDERS_CONFIG.stt.providers.map((p) => {
                          const config = getProviderConfig('stt', p);
                          return (
                            <SelectItem key={p} value={p}>
                              {config?.name || p}
                            </SelectItem>
                          );
                        })}
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
                      placeholder="Describe the purpose or use case for this STT configuration"
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

            <FormField
              control={form.control}
              name="api_key"
              render={({ field }) => (
                <FormItem className="col-span-2">
                  <FormLabel>
                    API Key <span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="Enter your API key" {...field} />
                  </FormControl>
                  <Alert variant="info" className="mt-2">
                    <AlertDescription>
                      <strong>Security Note:</strong> API keys are stored securely and never returned in API responses.
                    </AlertDescription>
                  </Alert>
                  <FormMessage />
                </FormItem>
              )}
            />

            {providerConfig?.parameters.language && (
              <FormField
                control={form.control}
                name="language"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Language (Optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="en-US, es-ES, fr-FR" {...field} />
                    </FormControl>
                    <FormDescription>
                      Language code (e.g., en-US, es-ES). Most providers support automatic detection.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {providerConfig &&
              Object.keys(providerConfig.parameters).filter((key) => key !== 'language').length > 0 && (
                <div className="rounded-lg border border-gray-200 p-4">
                  <h3 className="mb-4 font-medium text-gray-900">Provider Parameters</h3>
                  <div className="grid grid-cols-2 gap-6">
                    {Object.keys(providerConfig.parameters)
                      .filter((key) => key !== 'language')
                      .map((key) => renderParameterField(key))}
                  </div>
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

export default CreateSttConfigDialog;
