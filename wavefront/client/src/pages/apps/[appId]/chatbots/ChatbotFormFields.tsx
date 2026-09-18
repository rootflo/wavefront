import { NamespaceItem } from '@app/api/namespace-service';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import { Textarea } from '@app/components/ui/textarea';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import React from 'react';
import { UseFormReturn } from 'react-hook-form';

import { ChatbotFormValues, TEMPERATURE_MAX, TEMPERATURE_MIN } from './schemas';

interface ChatbotFormFieldsProps {
  form: UseFormReturn<ChatbotFormValues>;
  llmConfigs: LLMInferenceConfig[];
  namespaces: NamespaceItem[];
  /** Namespace is fixed at creation -- the update API does not accept it. */
  namespaceLocked?: boolean;
}

/**
 * Field set shared by the create and edit dialogs, so the two cannot drift on
 * validation or on the temperature handling.
 */
const ChatbotFormFields: React.FC<ChatbotFormFieldsProps> = ({
  form,
  llmConfigs,
  namespaces,
  namespaceLocked = false,
}) => {
  const selectedLlmConfigId = form.watch('llm_config_id');
  // A chatbot can outlive the LLM config it points at. Without a placeholder
  // entry the Select trigger would render empty and look like nothing was set.
  const selectedConfigMissing = !!selectedLlmConfigId && !llmConfigs.some((c) => c.id === selectedLlmConfigId);

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h3 className="text-sm font-semibold">Basic Information</h3>
        <div className="grid grid-cols-2 gap-6">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Name<span className="text-red-500">*</span>
                </FormLabel>
                <FormControl>
                  <Input placeholder="e.g., support-bot" maxLength={255} {...field} />
                </FormControl>
                <FormDescription>Letters, digits, underscores and hyphens; must start with a letter</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="namespace"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Namespace<span className="text-red-500">*</span>
                </FormLabel>
                <Select onValueChange={field.onChange} value={field.value} disabled={namespaceLocked}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select namespace" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {!namespaces.some((ns) => ns.name === 'default') && (
                      <SelectItem value="default">default</SelectItem>
                    )}
                    {namespaces.map((ns) => (
                      <SelectItem key={ns.name} value={ns.name}>
                        {ns.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  {namespaceLocked
                    ? 'Namespace cannot be changed after creation'
                    : 'Created automatically if it does not exist yet'}
                </FormDescription>
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
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea rows={2} maxLength={500} placeholder="Describe what this chatbot is for" {...field} />
              </FormControl>
              <FormDescription>{field.value?.length || 0}/500 characters</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-semibold">Prompt</h3>

        <FormField
          control={form.control}
          name="system_prompt"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                System Prompt<span className="text-red-500">*</span>
              </FormLabel>
              <FormControl>
                <Textarea
                  rows={10}
                  placeholder="You are a billing support agent. Answer only questions about invoices..."
                  className="font-mono text-xs"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Sent on every turn. Edits apply to new conversations only — existing ones keep the prompt they started
                with.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="welcome_message"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Welcome Message</FormLabel>
              <FormControl>
                <Textarea rows={2} placeholder="Hi! How can I help you today?" {...field} />
              </FormControl>
              <FormDescription>Stored as the first message of every new conversation</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-semibold">Model</h3>
        <div className="grid grid-cols-2 gap-6">
          <FormField
            control={form.control}
            name="llm_config_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  LLM Configuration<span className="text-red-500">*</span>
                </FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select LLM configuration" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {selectedConfigMissing && (
                      <SelectItem value={selectedLlmConfigId} disabled>
                        Unavailable config ({selectedLlmConfigId.slice(0, 8)}…)
                      </SelectItem>
                    )}
                    {llmConfigs.map((config) => (
                      <SelectItem key={config.id} value={config.id}>
                        {config.display_name} ({config.type})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {llmConfigs.length === 0 && (
                  <FormDescription className="text-amber-600">
                    No LLM configurations found. Create one first.
                  </FormDescription>
                )}
                {selectedConfigMissing && llmConfigs.length > 0 && (
                  <FormDescription className="text-amber-600">
                    The configured model no longer exists. Pick another one.
                  </FormDescription>
                )}
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="temperature"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Temperature</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    min={TEMPERATURE_MIN}
                    max={TEMPERATURE_MAX}
                    placeholder="Model default"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  Leave blank to use the model&apos;s own setting. 0 is a valid value and means fully deterministic.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="enabled"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <FormLabel>Enabled</FormLabel>
                <FormDescription>Disabled chatbots cannot be chatted with</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
      </div>
    </div>
  );
};

export default ChatbotFormFields;
