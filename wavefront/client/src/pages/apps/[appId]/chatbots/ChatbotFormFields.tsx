import { NamespaceItem } from '@app/api/namespace-service';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import { Textarea } from '@app/components/ui/textarea';
import { useGetAgentVersions } from '@app/hooks';
import { AgentListItem } from '@app/types/agent';
import { LLMInferenceConfig } from '@app/types/llm-inference-config';
import React from 'react';
import { UseFormReturn } from 'react-hook-form';

import { CHAT_TYPE_AGENT, CHAT_TYPE_LLM, ChatbotFormValues, TEMPERATURE_MAX, TEMPERATURE_MIN } from './schemas';

interface ChatbotFormFieldsProps {
  form: UseFormReturn<ChatbotFormValues>;
  appId: string;
  llmConfigs: LLMInferenceConfig[];
  agents: AgentListItem[];
  namespaces: NamespaceItem[];
  /** Namespace is fixed at creation -- the update API does not accept it. */
  namespaceLocked?: boolean;
  /** A chatbot keeps the type it was created as -- the update API rejects a switch. */
  chatTypeLocked?: boolean;
  /**
   * The version this chatbot is already pinned to, when editing one. The update
   * API can move a pin but not remove it, so "follow the current version" is
   * not offered while this is set.
   */
  pinnedAgentVersion?: number | null;
}

/** Stands in for "no pinned version": a Select item cannot have an empty value. */
const FOLLOW_CURRENT_VERSION = 'current';

/**
 * Field set shared by the create and edit dialogs, so the two cannot drift on
 * validation or on the temperature handling.
 */
const ChatbotFormFields: React.FC<ChatbotFormFieldsProps> = ({
  form,
  appId,
  llmConfigs,
  agents,
  namespaces,
  namespaceLocked = false,
  chatTypeLocked = false,
  pinnedAgentVersion = null,
}) => {
  const isAgentBacked = form.watch('chat_type') === CHAT_TYPE_AGENT;
  const selectedAgentId = form.watch('agent_id');
  // Agents are hard-deleted, so a chatbot can point at one that is gone. Same
  // placeholder treatment as a missing LLM config below.
  const selectedAgentMissing = !!selectedAgentId && !agents.some((agent) => agent.id === selectedAgentId);
  // The versions stored for the chosen agent. Soft-deleted ones cannot be run.
  const { data: agentVersions = [], isLoading: agentVersionsLoading } = useGetAgentVersions(
    appId,
    isAgentBacked && selectedAgentId && !selectedAgentMissing ? selectedAgentId : undefined
  );
  const availableVersions = agentVersions
    .filter((version) => !version.is_deleted)
    .sort((a, b) => b.version - a.version);
  const selectedAgentVersion = form.watch('agent_version');
  const selectedVersionMissing =
    !!selectedAgentVersion &&
    !agentVersionsLoading &&
    !availableVersions.some((version) => String(version.version) === selectedAgentVersion);
  // Unpinning is only possible where nothing is pinned yet.
  const canFollowCurrent = pinnedAgentVersion === null;
  const selectedLlmConfigId = form.watch('llm_config_id');
  // A chatbot can outlive the LLM config it points at. Without a placeholder
  // entry the Select trigger would render empty and look like nothing was set.
  const selectedConfigMissing = !!selectedLlmConfigId && !llmConfigs.some((c) => c.id === selectedLlmConfigId);

  return (
    <div className="space-y-6">
      <FormField
        control={form.control}
        name="chat_type"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              Chatbot Type<span className="text-red-500">*</span>
            </FormLabel>
            <Select onValueChange={field.onChange} value={field.value} disabled={chatTypeLocked}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select chatbot type" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value={CHAT_TYPE_LLM}>Direct LLM chat</SelectItem>
                <SelectItem value={CHAT_TYPE_AGENT}>Agent-backed chat</SelectItem>
              </SelectContent>
            </Select>
            <FormDescription>
              {chatTypeLocked
                ? 'The type cannot be changed after creation'
                : isAgentBacked
                  ? 'An agent answers: its prompt, model and tools are used, and it can call tools during a conversation'
                  : 'A system prompt is sent straight to a model, with no tools'}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

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

      {!isAgentBacked && (
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
        </div>
      )}

      {isAgentBacked && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold">Agent</h3>
          <div className="grid grid-cols-2 gap-6">
            <FormField
              control={form.control}
              name="agent_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Agent<span className="text-red-500">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={(value) => {
                      field.onChange(value);
                      // Versions belong to an agent, so a pin does not carry over.
                      form.setValue('agent_version', '', { shouldDirty: true, shouldValidate: true });
                    }}
                    value={field.value}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select agent" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {selectedAgentMissing && (
                        <SelectItem value={selectedAgentId} disabled>
                          Unavailable agent ({selectedAgentId.slice(0, 8)}…)
                        </SelectItem>
                      )}
                      {agents.map((agent) => (
                        <SelectItem key={agent.id} value={agent.id}>
                          {agent.name} ({agent.namespace})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {agents.length === 0 && (
                    <FormDescription className="text-amber-600">No agents found. Create one first.</FormDescription>
                  )}
                  {selectedAgentMissing && agents.length > 0 && (
                    <FormDescription className="text-amber-600">
                      The agent behind this chatbot no longer exists. Pick another one.
                    </FormDescription>
                  )}
                  {!selectedAgentMissing && agents.length > 0 && (
                    <FormDescription>
                      Its prompt, model and tools are used. An agent whose prompt needs variables cannot back a chatbot.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="agent_version"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Agent Version</FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(value === FOLLOW_CURRENT_VERSION ? '' : value)}
                    value={field.value === '' ? (canFollowCurrent ? FOLLOW_CURRENT_VERSION : '') : field.value}
                    disabled={!selectedAgentId || selectedAgentMissing}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder={selectedAgentId ? 'Select version' : 'Select an agent first'} />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {canFollowCurrent && (
                        <SelectItem value={FOLLOW_CURRENT_VERSION}>Current version (follows the agent)</SelectItem>
                      )}
                      {selectedVersionMissing && (
                        <SelectItem value={selectedAgentVersion} disabled>
                          v{selectedAgentVersion} (unavailable)
                        </SelectItem>
                      )}
                      {availableVersions.map((version) => (
                        <SelectItem key={version.id} value={String(version.version)}>
                          v{version.version}
                          {version.is_current ? ' (current)' : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {selectedVersionMissing ? (
                    <FormDescription className="text-amber-600">
                      The pinned version no longer exists. Pick another one.
                    </FormDescription>
                  ) : (
                    <FormDescription>
                      {canFollowCurrent
                        ? 'Pin a stored version, or follow whichever is current. Conversations keep the version they started on.'
                        : 'This chatbot is pinned to a version. It can be moved to another, but not unpinned.'}
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </div>
      )}

      <div className="space-y-4">
        <h3 className="text-sm font-semibold">Conversation</h3>

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

      {!isAgentBacked && (
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
        </div>
      )}

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
  );
};

export default ChatbotFormFields;
