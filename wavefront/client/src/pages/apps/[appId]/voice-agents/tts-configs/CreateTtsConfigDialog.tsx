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
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const createTtsConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.string().min(1, 'Provider is required'),
  voice_id: z.string().min(1, 'Voice ID is required'),
  api_key: z.string().min(1, 'API key is required'),
  language: z.string().optional(),
});

type CreateTtsConfigInput = z.infer<typeof createTtsConfigSchema>;

interface CreateTtsConfigDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const CreateTtsConfigDialog: React.FC<CreateTtsConfigDialogProps> = ({ isOpen, onOpenChange, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);

  const form = useForm<CreateTtsConfigInput>({
    resolver: zodResolver(createTtsConfigSchema),
    defaultValues: {
      display_name: '',
      description: '',
      provider: 'elevenlabs',
      voice_id: '',
      api_key: '',
      language: '',
    },
  });

  const watchedProvider = form.watch('provider');

  // Reset parameters when provider changes
  useEffect(() => {
    if (isOpen && watchedProvider) {
      setParameters(initializeParameters('tts', watchedProvider));
    }
  }, [watchedProvider, isOpen]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        display_name: '',
        description: '',
        provider: 'elevenlabs',
        voice_id: '',
        api_key: '',
        language: '',
      });
      setParameters({});
    }
  }, [isOpen, form]);

  const setParameter = (key: string, value: unknown) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const buildParameters = () => {
    const config = getProviderConfig('tts', watchedProvider);
    if (!config) return null;

    const params: Record<string, unknown> = {};

    Object.entries(parameters).forEach(([key, value]) => {
      const paramConfig = config.parameters[key];
      if (!paramConfig) return;

      if (value === paramConfig.default && (value === '' || value === undefined)) {
        return;
      }

      if (paramConfig.type === 'array' && typeof value === 'string') {
        const arr = value
          .split(',')
          .map((v) => v.trim())
          .filter(Boolean);
        if (arr.length > 0) {
          params[key] = arr;
        }
      } else if (value !== '' && value !== undefined) {
        params[key] = value;
      }
    });

    return Object.keys(params).length > 0 ? params : null;
  };

  const onSubmit = async (data: CreateTtsConfigInput) => {
    setLoading(true);
    try {
      await floConsoleService.ttsConfigService.createTtsConfig({
        display_name: data.display_name.trim(),
        description: data.description?.trim() || null,
        provider: data.provider,
        voice_id: data.voice_id.trim(),
        api_key: data.api_key.trim(),
        language: data.language?.trim() || null,
        parameters: buildParameters(),
      });
      notifySuccess('TTS configuration created successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create TTS configuration');
    } finally {
      setLoading(false);
    }
  };

  const renderParameterField = (key: string) => {
    const config = getProviderConfig('tts', watchedProvider);
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
                value={value?.toString() ?? paramConfig.default?.toString() ?? ''}
                onValueChange={(val) => setParameter(key, val ? parseFloat(val) : undefined)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {paramConfig.options.map((option) => (
                    <SelectItem key={option} value={option.toString()}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {paramConfig.description && (
                <p className="text-muted-foreground text-[0.8rem]">{paramConfig.description}</p>
              )}
            </div>
          );
        }

        if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
          return (
            <div key={key} className="col-span-2 space-y-2">
              <Label>
                {paramConfig.description || key}: {value?.toFixed(2) || paramConfig.default}
              </Label>
              <Slider
                min={paramConfig.min}
                max={paramConfig.max}
                step={paramConfig.step || 1}
                value={[value ?? paramConfig.default]}
                onValueChange={(values: number[]) => setParameter(key, values[0])}
              />
              <p className="text-muted-foreground text-[0.8rem]">
                {paramConfig.min} - {paramConfig.max}
              </p>
            </div>
          );
        }

        return (
          <div key={key} className="space-y-2">
            <Label>
              {paramConfig.description || key} {key === 'sample_rate' || key === 'speed' ? '(Optional)' : ''}
            </Label>
            <Input
              type="number"
              value={value ?? ''}
              onChange={(e) => setParameter(key, e.target.value ? parseFloat(e.target.value) : undefined)}
              placeholder={paramConfig.placeholder}
              step={paramConfig.step}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">e.g., {paramConfig.placeholder}</p>
            )}
          </div>
        );

      case 'array':
        return (
          <div key={key} className="col-span-2 space-y-2">
            <Label>{paramConfig.description || key} (Optional)</Label>
            <Input
              type="text"
              value={Array.isArray(value) ? value.join(', ') : value || ''}
              onChange={(e) => setParameter(key, e.target.value)}
              placeholder={paramConfig.placeholder}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">{paramConfig.placeholder}</p>
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

  const providerConfig = getProviderConfig('tts', watchedProvider);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create TTS Configuration</DialogTitle>
          <DialogDescription>Configure a new Text-to-Speech provider</DialogDescription>
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
                      <Input placeholder="e.g., ElevenLabs English Voice" maxLength={100} {...field} />
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
                        {VOICE_PROVIDERS_CONFIG.tts.providers.map((p) => {
                          const config = getProviderConfig('tts', p);
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
                      placeholder="Describe the purpose or use case for this TTS configuration"
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
                name="voice_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Voice ID <span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder={watchedProvider === 'deepgram' ? 'aura-2-helena-en' : 'voice_id'}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {watchedProvider === 'deepgram'
                        ? 'For Deepgram, voice_id IS the model (e.g., aura-2-helena-en)'
                        : 'Provider-specific voice identifier'}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      API Key <span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="Enter your API key" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <Alert variant="info">
              <AlertDescription>
                <strong>Security Note:</strong> API keys are stored securely and never returned in API responses.
              </AlertDescription>
            </Alert>

            {providerConfig?.parameters.language && (
              <FormField
                control={form.control}
                name="language"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Language (Optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="en, es, fr" {...field} />
                    </FormControl>
                    <FormDescription>ISO 639-1 language code (e.g., en, es, fr)</FormDescription>
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
              <Button type="submit" disabled={loading}>
                {loading ? 'Creating...' : 'Create Configuration'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTtsConfigDialog;
