import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form } from '@app/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { getProviderConfig, groupParamKeys, initializeParameters } from '@app/config/voice-providers';
import { useCreateVoiceAgent, useGetSttConfigs, useGetTtsConfigs, useUpdateVoiceAgent } from '@app/hooks';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { VoiceAgent } from '@app/types/voice-agent';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useMemo, useState } from 'react';
import { FieldErrors, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import ConversationConfigField from './ConversationConfigField';
import ConversationConfigGuide from './ConversationConfigGuide';
import VoiceAgentToolsManager, { PendingAgentTool } from './VoiceAgentToolsManager';
import BasicInfoSection from './form/BasicInfoSection';
import BehaviorSection from './form/BehaviorSection';
import ConfigurationsSection from './form/ConfigurationsSection';
import LanguagesSection from './form/LanguagesSection';
import {
  buildSchema,
  FIELD_TAB_MAP,
  FORM_TAB,
  FormTab,
  hasCustomVoices,
  isFormTab,
  ParameterKind,
  toFormValues,
  VoiceAgentInput,
} from './form/voice-agent-form';
import { VoiceAgentFields, buildVoiceAgentFields, changedFields, toCreateRequest } from './form/voice-agent-request';

const SUBMIT_LABEL = { create: 'Create Voice Agent', edit: 'Update Voice Agent' };

interface VoiceAgentFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  /** The agent to edit; omit to create one. Render separate instances for create and edit. */
  agent?: VoiceAgent;
}

const VoiceAgentFormDialog: React.FC<VoiceAgentFormDialogProps> = ({ isOpen, onOpenChange, appId, agent }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const createVoiceAgent = useCreateVoiceAgent(appId);
  const updateVoiceAgent = useUpdateVoiceAgent(appId);
  const isEdit = !!agent;
  const saving = createVoiceAgent.isPending || updateVoiceAgent.isPending;
  const [activeTab, setActiveTab] = useState<FormTab>(FORM_TAB.BASIC);
  const [ttsParameters, setTtsParameters] = useState<Record<string, unknown>>({});
  const [sttParameters, setSttParameters] = useState<Record<string, unknown>>({});
  const [voiceIdState, setVoiceIdState] = useState<Record<string, string>>(agent?.tts_voice_ids || { en: '' });
  const [customizeVoicesPerLanguage, setCustomizeVoicesPerLanguage] = useState(() => hasCustomVoices(agent));
  // Tools picked before a new agent exists; an existing agent attaches them directly
  const [pendingTools, setPendingTools] = useState<PendingAgentTool[]>([]);

  // Fetch configs for dropdowns
  const { data: ttsConfigs = [] } = useGetTtsConfigs(appId);
  const { data: sttConfigs = [] } = useGetSttConfigs(appId);

  const schema = useMemo(() => buildSchema(isEdit), [isEdit]);
  const form = useForm<VoiceAgentInput>({
    resolver: zodResolver(schema),
    defaultValues: toFormValues(agent),
  });

  // Watch config selections to determine providers
  const watchedTtsConfigId = form.watch('tts_config_id');
  const watchedSttConfigId = form.watch('stt_config_id');
  const watchedSupportedLanguages = form.watch('supported_languages');

  // Get selected providers
  const selectedTtsProvider = ttsConfigs.find((c) => c.id === watchedTtsConfigId)?.provider;
  const selectedSttProvider = sttConfigs.find((c) => c.id === watchedSttConfigId)?.provider;

  // The providers the agent was saved with, so its stored settings load only while those stay selected
  const savedTtsProvider = ttsConfigs.find((c) => c.id === agent?.tts_config_id)?.provider;
  const savedSttProvider = sttConfigs.find((c) => c.id === agent?.stt_config_id)?.provider;

  // A provider starts from its defaults; the saved provider of an existing agent starts from its stored values
  useEffect(() => {
    if (!isOpen || !selectedTtsProvider) return;
    setTtsParameters(
      agent && selectedTtsProvider === savedTtsProvider
        ? agent.tts_parameters || {}
        : initializeParameters('tts', selectedTtsProvider)
    );
  }, [selectedTtsProvider, savedTtsProvider, agent, isOpen]);

  useEffect(() => {
    if (!isOpen || !selectedSttProvider) return;
    setSttParameters(
      agent && selectedSttProvider === savedSttProvider
        ? agent.stt_parameters || {}
        : initializeParameters('stt', selectedSttProvider)
    );
  }, [selectedSttProvider, savedSttProvider, agent, isOpen]);

  // Sync voice ID state with language changes (keep shared default when not customizing)
  useEffect(() => {
    if (isOpen && watchedSupportedLanguages) {
      setVoiceIdState((prev) => {
        const shared = Object.values(prev).find((value) => value) || '';
        const newState: Record<string, string> = {};
        watchedSupportedLanguages.forEach((lang) => {
          newState[lang] = customizeVoicesPerLanguage ? prev[lang] || shared : shared || prev[lang] || '';
        });
        form.setValue('tts_voice_ids', newState);
        return newState;
      });
    }
  }, [watchedSupportedLanguages, isOpen, customizeVoicesPerLanguage, form]);

  // Start from the agent being edited, or a blank form, each time the dialog opens
  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(agent));
      setVoiceIdState(agent?.tts_voice_ids || { en: '' });
      setCustomizeVoicesPerLanguage(hasCustomVoices(agent));
      setPendingTools([]);
      setActiveTab(FORM_TAB.BASIC);
    } else {
      setTtsParameters({});
      setSttParameters({});
    }
  }, [isOpen, agent, form]);

  const onInvalid = (errors: FieldErrors<VoiceAgentInput>) => {
    const firstErrorField = Object.keys(errors)[0] as keyof VoiceAgentInput | undefined;
    if (firstErrorField && FIELD_TAB_MAP[firstErrorField]) {
      setActiveTab(FIELD_TAB_MAP[firstErrorField]);
    }
  };

  /** An update sends only what changed; with nothing changed there's nothing to save. */
  const saveChanges = (existing: VoiceAgent, fields: VoiceAgentFields) => {
    const changes = changedFields(fields, existing);
    if (Object.keys(changes).length === 0) {
      notifySuccess('No changes to update');
      onOpenChange(false);
      return;
    }
    updateVoiceAgent.mutate({ agentId: existing.id, data: changes }, { onSuccess: () => onOpenChange(false) });
  };

  /** Creates the agent with the tools picked so far, then opens it. */
  const create = (fields: VoiceAgentFields) => {
    createVoiceAgent.mutate(
      { data: toCreateRequest(fields), tools: pendingTools },
      {
        onSuccess: ({ voiceAgentId, failedToolCount }) => {
          if (failedToolCount > 0) {
            notifyError(
              `Voice agent created, but ${failedToolCount} tool(s) could not be attached. Attach them from Edit.`
            );
          }
          onOpenChange(false);
          if (voiceAgentId) navigate(`/apps/${appId}/voice-agents/${voiceAgentId}`);
        },
      }
    );
  };

  const onSubmit = (data: VoiceAgentInput) => {
    const result = buildVoiceAgentFields(data, {
      tts: { values: ttsParameters, supported: ttsProviderConfig?.parameters },
      stt: { values: sttParameters, supported: sttProviderConfig?.parameters },
    });
    if (!result.ok) {
      notifyError(result.error);
      return;
    }
    if (agent) saveChanges(agent, result.fields);
    else create(result.fields);
  };

  // TTS and STT provider settings share one renderer; `kind` picks the provider and the state it edits
  const parameterState: Record<
    ParameterKind,
    { provider?: string; values: Record<string, unknown>; set: (key: string, value: unknown) => void }
  > = {
    tts: {
      provider: selectedTtsProvider,
      values: ttsParameters,
      set: (key, value) => setTtsParameters((prev) => ({ ...prev, [key]: value })),
    },
    stt: {
      provider: selectedSttProvider,
      values: sttParameters,
      set: (key, value) => setSttParameters((prev) => ({ ...prev, [key]: value })),
    },
  };

  const ttsProviderConfig = selectedTtsProvider ? getProviderConfig('tts', selectedTtsProvider) : null;
  const sttProviderConfig = selectedSttProvider ? getProviderConfig('stt', selectedSttProvider) : null;
  const ttsParamGroups = ttsProviderConfig ? groupParamKeys(ttsProviderConfig.parameters) : null;
  const sttParamGroups = sttProviderConfig ? groupParamKeys(sttProviderConfig.parameters) : null;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[760px] max-h-[calc(100vh-2rem)] max-w-4xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>{isEdit ? 'Edit Voice Agent' : 'Create New Voice Agent'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update the voice agent configuration for' : 'Create a new voice agent for'}{' '}
            {selectedApp?.app_name}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="flex min-h-0 flex-1 flex-col">
            <Tabs
              value={activeTab}
              onValueChange={(value) => {
                if (isFormTab(value)) setActiveTab(value);
              }}
              className="flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <TabsList className="flex w-full shrink-0 [&>button]:flex-1 [&>button]:px-2">
                <TabsTrigger value={FORM_TAB.BASIC}>Basic Info</TabsTrigger>
                <TabsTrigger value={FORM_TAB.BEHAVIOR}>Behavior</TabsTrigger>
                <TabsTrigger value={FORM_TAB.CONFIGURATIONS}>Configurations</TabsTrigger>
                <TabsTrigger value={FORM_TAB.LANGUAGES}>Languages</TabsTrigger>
                <TabsTrigger value={FORM_TAB.TOOLS}>Tools</TabsTrigger>
                <TabsTrigger value={FORM_TAB.ADVANCED}>Advanced</TabsTrigger>
                <TabsTrigger value={FORM_TAB.GUIDE}>Guide</TabsTrigger>
              </TabsList>

              <TabsContent value={FORM_TAB.BASIC} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <BasicInfoSection />
              </TabsContent>

              <TabsContent value={FORM_TAB.CONFIGURATIONS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <ConfigurationsSection
                  appId={appId}
                  parameters={parameterState}
                  ttsParamGroups={ttsParamGroups}
                  sttParamGroups={sttParamGroups}
                  voiceIdState={voiceIdState}
                  setVoiceIdState={setVoiceIdState}
                  customizeVoicesPerLanguage={customizeVoicesPerLanguage}
                  setCustomizeVoicesPerLanguage={setCustomizeVoicesPerLanguage}
                />
              </TabsContent>

              <TabsContent value={FORM_TAB.LANGUAGES} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <LanguagesSection isEdit={isEdit} />
              </TabsContent>

              <TabsContent
                value={FORM_TAB.BEHAVIOR}
                className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden"
              >
                <BehaviorSection />
              </TabsContent>

              <TabsContent value={FORM_TAB.TOOLS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                {agent ? (
                  <VoiceAgentToolsManager appId={appId} agentId={agent.id} />
                ) : (
                  <VoiceAgentToolsManager
                    appId={appId}
                    pendingTools={pendingTools}
                    onPendingToolsChange={setPendingTools}
                  />
                )}
              </TabsContent>

              <TabsContent value={FORM_TAB.ADVANCED} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <ConversationConfigField
                  form={form}
                  name="conversation_config"
                  hasWelcomeMessage={!!form.watch('welcome_message')?.trim()}
                  isMultiLanguage={(watchedSupportedLanguages?.length ?? 0) > 1}
                />
              </TabsContent>

              <TabsContent value={FORM_TAB.GUIDE} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <ConversationConfigGuide />
              </TabsContent>
            </Tabs>

            <DialogFooter className="shrink-0 pt-4">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {SUBMIT_LABEL[isEdit ? 'edit' : 'create']}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default VoiceAgentFormDialog;
