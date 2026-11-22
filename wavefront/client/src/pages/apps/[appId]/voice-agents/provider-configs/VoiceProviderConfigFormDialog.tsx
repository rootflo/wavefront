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
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import { VOICE_PROVIDERS_CONFIG, getProviderConfig } from '@app/config/voice-providers';
import {
  UpdateVoiceProviderConfigRequest,
  VoiceProviderKind,
  useCreateVoiceProviderConfig,
  useUpdateVoiceProviderConfig,
} from '@app/hooks';
import { SttConfig, SttProvider } from '@app/types/stt-config';
import { TtsConfig, TtsProvider } from '@app/types/tts-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { useParams } from 'react-router';
import { z } from 'zod';
import { VOICE_PROVIDER_KINDS } from './kinds';

export type VoiceProviderConfig = SttConfig | TtsConfig;

/** The stored key is never sent back; the placeholder shows whether one is set. */
const apiKeyPlaceholder = (config?: VoiceProviderConfig): string => {
  if (!config) return 'Enter your API key';
  return config.has_api_key ? '******** (set) - enter a new key to replace it' : 'Enter new API key to update';
};

const buildSchema = (kind: VoiceProviderKind, isEdit: boolean) =>
  z
    .object({
      display_name: z
        .string()
        .min(1, 'Display name is required')
        .max(100, 'Display name must be 100 characters or less'),
      description: z.string().max(500, 'Description must be 500 characters or less').optional(),
      provider: z.enum(VOICE_PROVIDERS_CONFIG[kind].providers as unknown as [string, ...string[]]),
      // Editing keeps the stored key when the field is left empty
      api_key: isEdit ? z.string().optional() : z.string().trim().min(1, 'API key is required'),
      region: z.string().optional(),
    })
    .refine((data) => data.provider !== 'azure' || (data.region && data.region.trim().length > 0), {
      message: 'Region is required for Azure',
      path: ['region'],
    });

type ConfigInput = z.infer<ReturnType<typeof buildSchema>>;

const toFormValues = (kind: VoiceProviderKind, config?: VoiceProviderConfig): ConfigInput => ({
  display_name: config?.display_name ?? '',
  description: config?.description ?? '',
  provider: config?.provider ?? VOICE_PROVIDER_KINDS[kind].defaultProvider,
  api_key: '',
  region: config?.region ?? '',
});

const SUBMIT_LABEL = {
  create: { idle: 'Create Configuration', busy: 'Creating...' },
  edit: { idle: 'Update Configuration', busy: 'Updating...' },
};

interface VoiceProviderConfigFormDialogProps {
  kind: VoiceProviderKind;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** The config to edit; omit to create a new one. Render separate instances for create and edit. */
  config?: VoiceProviderConfig;
}

const VoiceProviderConfigFormDialog: React.FC<VoiceProviderConfigFormDialogProps> = ({
  kind,
  isOpen,
  onOpenChange,
  config,
}) => {
  const { app } = useParams<{ app: string }>();
  const createConfig = useCreateVoiceProviderConfig(kind, app);
  const updateConfig = useUpdateVoiceProviderConfig(kind, app);
  const { label, title, namePlaceholder } = VOICE_PROVIDER_KINDS[kind];
  const isEdit = !!config;
  const saving = createConfig.isPending || updateConfig.isPending;

  const schema = useMemo(() => buildSchema(kind, isEdit), [kind, isEdit]);
  const form = useForm<ConfigInput>({
    resolver: zodResolver(schema),
    defaultValues: toFormValues(kind, config),
  });

  const selectedProvider = form.watch('provider');

  // Start from the config being edited, or a blank form, each time the dialog opens
  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(kind, config));
    }
  }, [isOpen, kind, config, form]);

  const close = () => onOpenChange(false);

  const onSubmit = (data: ConfigInput) => {
    const display_name = data.display_name.trim();
    const description = data.description?.trim() || null;
    const region = data.region?.trim() || null;
    const api_key = data.api_key?.trim();

    if (config) {
      const updateData: UpdateVoiceProviderConfigRequest = { display_name, description, region };
      if (api_key) {
        updateData.api_key = api_key;
      }
      updateConfig.mutate({ configId: config.id, data: updateData }, { onSuccess: close });
    } else {
      createConfig.mutate(
        {
          display_name,
          description,
          region,
          provider: data.provider as SttProvider | TtsProvider,
          api_key: api_key ?? '',
        },
        { onSuccess: close }
      );
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${label} Configuration` : `Create ${label} Configuration`}</DialogTitle>
          <DialogDescription>
            {isEdit ? `Update the ${title} provider configuration` : `Configure a new ${title} provider`}
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
                      <Input placeholder={namePlaceholder} maxLength={100} {...field} />
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
                    {/* The provider is fixed once a config exists */}
                    <Select onValueChange={field.onChange} value={field.value} disabled={isEdit}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {VOICE_PROVIDERS_CONFIG[kind].providers.map((p) => {
                          const providerConfig = getProviderConfig(kind, p);
                          return (
                            <SelectItem key={p} value={p}>
                              {providerConfig?.name || p}
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
                      placeholder={`Describe the purpose or use case for this ${label} configuration`}
                      maxLength={500}
                      rows={3}
                      {...field}
                    />
                  </FormControl>
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
                    {isEdit ? (
                      'API Key (Optional - leave empty to keep existing)'
                    ) : (
                      <>
                        API Key <span className="text-red-500">*</span>
                      </>
                    )}
                  </FormLabel>
                  <FormControl>
                    <Input type="password" placeholder={apiKeyPlaceholder(config)} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {selectedProvider === 'azure' && (
              <FormField
                control={form.control}
                name="region"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Region <span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., eastus, westus2" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <Alert variant="info">
              <AlertDescription>
                <strong>Security Note:</strong> {isEdit && 'Leave empty to keep the existing API key. '}API keys are
                stored securely and never returned in API responses.
              </AlertDescription>
            </Alert>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={close} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {SUBMIT_LABEL[isEdit ? 'edit' : 'create'][saving ? 'busy' : 'idle']}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default VoiceProviderConfigFormDialog;
