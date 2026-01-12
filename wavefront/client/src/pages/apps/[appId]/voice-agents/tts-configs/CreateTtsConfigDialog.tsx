import floConsoleService from '@app/api';
import { Alert, AlertDescription } from '@app/components/ui/alert';
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
import { VOICE_PROVIDERS_CONFIG, getProviderConfig } from '@app/config/voice-providers';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const createTtsConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.enum(['elevenlabs', 'deepgram', 'cartesia'] as [string, ...string[]]),
  api_key: z.string().min(1, 'API key is required'),
});

type CreateTtsConfigInput = z.infer<typeof createTtsConfigSchema>;

interface CreateTtsConfigDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const CreateTtsConfigDialog: React.FC<CreateTtsConfigDialogProps> = ({ isOpen, onOpenChange, onSuccess }) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loading, setLoading] = useState(false);

  const form = useForm<CreateTtsConfigInput>({
    resolver: zodResolver(createTtsConfigSchema),
    defaultValues: {
      display_name: '',
      description: '',
      provider: 'elevenlabs',
      api_key: '',
    },
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        display_name: '',
        description: '',
        provider: 'elevenlabs',
        api_key: '',
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateTtsConfigInput) => {
    setLoading(true);
    try {
      await floConsoleService.ttsConfigService.createTtsConfig({
        display_name: data.display_name.trim(),
        description: data.description?.trim() || null,
        provider: data.provider as 'elevenlabs' | 'deepgram' | 'cartesia',
        api_key: data.api_key.trim(),
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
                      <Input placeholder="e.g., ElevenLabs Production" maxLength={100} {...field} />
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
                <FormItem>
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

            <Alert variant="info">
              <AlertDescription>
                <strong>Security Note:</strong> API keys are stored securely and never returned in API responses.
              </AlertDescription>
            </Alert>

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
