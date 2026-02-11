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
import { SttConfig, UpdateSttConfigRequest } from '@app/types/stt-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const updateSttConfigSchema = z.object({
  display_name: z.string().min(1, 'Display name is required').max(100, 'Display name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  provider: z.enum(['deepgram', 'sarvam'] as [string, ...string[]]),
  api_key: z.string().optional(),
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
  const [loading, setLoading] = useState(false);

  const form = useForm<UpdateSttConfigInput>({
    resolver: zodResolver(updateSttConfigSchema),
    defaultValues: {
      display_name: config.display_name,
      description: config.description || '',
      provider: config.provider,
      api_key: '',
    },
  });

  // Reset form when dialog opens or config changes
  useEffect(() => {
    if (isOpen && config) {
      form.reset({
        display_name: config.display_name,
        description: config.description || '',
        provider: config.provider,
        api_key: '',
      });
    }
  }, [isOpen, config, form]);

  const onSubmit = async (data: UpdateSttConfigInput) => {
    setLoading(true);
    try {
      const updateData: UpdateSttConfigRequest = {
        display_name: data.display_name.trim(),
        description: data.description?.trim() || null,
      };

      if (data.api_key?.trim()) {
        updateData.api_key = data.api_key.trim();
      }

      await floConsoleService.sttConfigService.updateSttConfig(config.id, updateData);
      notifySuccess('STT configuration updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update STT configuration');
    } finally {
      setLoading(false);
    }
  };

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
                      <Input placeholder="e.g., Deepgram Production" maxLength={100} {...field} />
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
                    <Select onValueChange={field.onChange} value={field.value} disabled>
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
                    <FormDescription>Provider cannot be changed after creation</FormDescription>
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
                <FormItem>
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

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Updating...' : 'Update Configuration'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditSttConfigDialog;
