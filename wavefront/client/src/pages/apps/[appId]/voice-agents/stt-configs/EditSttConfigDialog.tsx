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
import { VOICE_PROVIDERS_CONFIG, getProviderConfig, mergeParameters } from '@app/config/voice-providers';
import { useNotifyStore } from '@app/store';
import { SttConfig, UpdateSttConfigRequest } from '@app/types/stt-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const updateSttConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.string().min(1, 'Provider is required'),
  api_key: z.string().optional(),
  language: z.string().optional(),
});

type UpdateSttConfigInput = z.infer<typeof updateSttConfigSchema>;

interface EditSttConfigDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  config: SttConfig;
  onSuccess?: () => void;
}

const EditSttConfigDialog: React.FC<EditSttConfigDialogProps> = ({ isOpen, onOpenChange, config, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [parameters, setParameters] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);

  const form = useForm<UpdateSttConfigInput>({
    resolver: zodResolver(updateSttConfigSchema),
    defaultValues: {
      display_name: config.display_name,
      description: config.description || '',
      provider: config.provider,
      api_key: '',
      language: config.language || '',
    },
  });

  const watchedProvider = form.watch('provider');

  // Initialize parameters when dialog opens or config changes
  useEffect(() => {
    if (isOpen && config) {
      form.reset({
        display_name: config.display_name,
        description: config.description || '',
        provider: config.provider,
        api_key: '',
        language: config.language || '',
      });
      // Merge saved parameters with defaults from config
      setParameters(mergeParameters('stt', config.provider, config.parameters));
    }
  }, [isOpen, config, form]);

  // Reset parameters when provider changes
  useEffect(() => {
    if (isOpen && watchedProvider && watchedProvider !== config.provider) {
      setParameters(mergeParameters('stt', watchedProvider, null));
    }
  }, [watchedProvider, isOpen, config.provider]);

  const setParameter = (key: string, value: any) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const buildParameters = () => {
    const providerConfig = getProviderConfig('stt', watchedProvider);
    if (!providerConfig) return null;

    const params: Record<string, any> = {};

    Object.entries(parameters).forEach(([key, value]) => {
      const paramConfig = providerConfig.parameters[key];
      if (!paramConfig) return;

      if (value !== '' && value !== undefined) {
        params[key] = value;
      }
    });

    return Object.keys(params).length > 0 ? params : null;
  };

  const onSubmit = async (data: UpdateSttConfigInput) => {
    setLoading(true);
    try {
      const updateData: UpdateSttConfigRequest = {
        display_name: data.display_name.trim(),
        description: data.description?.trim() || null,
        provider: data.provider as any,
        language: data.language?.trim() || null,
        parameters: buildParameters(),
      };

      if (data.api_key?.trim()) {
        updateData.api_key = data.api_key.trim();
      }

      await floConsoleService.sttConfigService.updateSttConfig(config.id, updateData);
      notifySuccess('STT configuration updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error: any) {
      notifyError(error?.response?.data?.error?.message || 'Failed to update STT configuration');
    } finally {
      setLoading(false);
    }
  };

  const renderParameterField = (key: string) => {
    const providerConfig = getProviderConfig('stt', watchedProvider);
    if (!providerConfig) return null;

    const paramConfig = providerConfig.parameters[key];
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
          <DialogTitle>Edit STT Configuration</DialogTitle>
          <DialogDescription>Update the Speech-to-Text provider configuration</DialogDescription>
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
                  <FormLabel>API Key (Optional - leave empty to keep existing)</FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="Enter new API key to update" {...field} />
                  </FormControl>
                  <Alert variant="info" className="mt-2">
                    <AlertDescription>
                      <strong>Security Note:</strong> Leave empty to keep the existing API key. API keys are stored
                      securely and never returned in API responses.
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
                Update Configuration
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditSttConfigDialog;
