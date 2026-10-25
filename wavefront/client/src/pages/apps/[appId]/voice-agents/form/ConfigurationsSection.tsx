import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetLLMConfigs, useGetSttConfigs, useGetTelephonyConfigs, useGetTtsConfigs } from '@app/hooks';
import FieldHelp from '@app/components/FieldHelp';
import { VoiceIdsSection } from '../VoiceIdsSection';
import { getTelephonyProviderConfig } from '@app/config/telephony-providers';
import { getVoiceProviderLabel } from '@app/config/voice-providers';
import { TelephonyProvider } from '@app/types/telephony-config';
import { useFormContext } from 'react-hook-form';
import { VoiceAgentInput, ParameterKind } from './voice-agent-form';
import ProviderParameterField, { ParameterState } from './ProviderParameterField';
import { ParamKeyGroups } from '@app/config/voice-providers';

interface ConfigurationsSectionProps {
  appId: string;
  /** The selected TTS and STT providers' settings, and how to change them. */
  parameters: Record<ParameterKind, ParameterState>;
  ttsParamGroups: ParamKeyGroups | null;
  sttParamGroups: ParamKeyGroups | null;
  voiceIdState: Record<string, string>;
  setVoiceIdState: (voiceIds: Record<string, string>) => void;
  customizeVoicesPerLanguage: boolean;
  setCustomizeVoicesPerLanguage: (customize: boolean) => void;
}

/** The models, speech providers, voices and phone line the agent uses. */
const ConfigurationsSection = ({
  appId,
  parameters,
  ttsParamGroups,
  sttParamGroups,
  voiceIdState,
  setVoiceIdState,
  customizeVoicesPerLanguage,
  setCustomizeVoicesPerLanguage,
}: ConfigurationsSectionProps) => {
  const form = useFormContext<VoiceAgentInput>();
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: ttsConfigs = [] } = useGetTtsConfigs(appId);
  const { data: sttConfigs = [] } = useGetSttConfigs(appId);
  const { data: telephonyConfigs = [] } = useGetTelephonyConfigs(appId);
  const watchedSupportedLanguages = form.watch('supported_languages');
  const selectedTtsProvider = parameters.tts.provider;
  const ttsParameters = parameters.tts.values;
  const renderParameterField = (kind: ParameterKind, key: string) => (
    <ProviderParameterField key={key} kind={kind} paramKey={key} {...parameters[kind]} />
  );

  return (
    <>
      {/* 1. Speech input (STT) */}
      <section className="space-y-4 rounded-md border p-4">
        <div className="flex items-center gap-1.5">
          <h4 className="text-base font-semibold tracking-tight">Speech input</h4>
          <FieldHelp ariaLabel="About speech input">How the agent hears the caller</FieldHelp>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="stt_config_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="frost-text-muted">
                    Provider<span className="text-red-500">*</span>
                  </FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select STT configuration" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {sttConfigs.map((config) => (
                        <SelectItem key={config.id} value={config.id}>
                          {getVoiceProviderLabel('stt', config.provider)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            {sttParamGroups?.compact.map((key) => renderParameterField('stt', key))}
          </div>
          {sttParamGroups && sttParamGroups.sliders.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {sttParamGroups.sliders.map((key) => renderParameterField('stt', key))}
            </div>
          )}
          {sttParamGroups && sttParamGroups.booleans.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {sttParamGroups.booleans.map((key) => renderParameterField('stt', key))}
            </div>
          )}
        </div>
      </section>

      {/* 2. Intelligence (LLM) */}
      <section className="space-y-4 rounded-md border p-4">
        <div className="flex items-center gap-1.5">
          <h4 className="text-base font-semibold tracking-tight">Intelligence</h4>
          <FieldHelp ariaLabel="About intelligence">The model that decides what to say</FieldHelp>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="llm_config_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="frost-text-muted">
                  Provider<span className="text-red-500">*</span>
                </FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a model" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {llmConfigs.map((config) => (
                      <SelectItem key={config.id} value={config.id}>
                        {config.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </section>

      {/* 3. Speech output (TTS) */}
      <section className="space-y-4 rounded-md border p-4">
        <div className="flex items-center gap-1.5">
          <h4 className="text-base font-semibold tracking-tight">Speech output</h4>
          <FieldHelp ariaLabel="About speech output">How the agent speaks back</FieldHelp>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="tts_config_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="frost-text-muted">
                    Provider<span className="text-red-500">*</span>
                  </FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select TTS configuration" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {ttsConfigs.map((config) => (
                        <SelectItem key={config.id} value={config.id}>
                          {getVoiceProviderLabel('tts', config.provider)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            {ttsParamGroups?.compact.map((key) => renderParameterField('tts', key))}
          </div>
          {ttsParamGroups && ttsParamGroups.sliders.length > 0 && (
            <div className="grid grid-cols-1 gap-x-4 gap-y-8 sm:grid-cols-2">
              {ttsParamGroups.sliders.map((key) => renderParameterField('tts', key))}
            </div>
          )}
          {ttsParamGroups && ttsParamGroups.booleans.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {ttsParamGroups.booleans.map((key) => renderParameterField('tts', key))}
            </div>
          )}
          {selectedTtsProvider && (
            <FormField
              control={form.control}
              name="tts_voice_ids"
              render={({ field }) => (
                <FormItem>
                  <VoiceIdsSection
                    provider={selectedTtsProvider}
                    model={typeof ttsParameters.model === 'string' ? ttsParameters.model : undefined}
                    languages={watchedSupportedLanguages}
                    voiceIds={voiceIdState}
                    customizePerLanguage={customizeVoicesPerLanguage}
                    onCustomizePerLanguageChange={setCustomizeVoicesPerLanguage}
                    onChange={(next) => {
                      setVoiceIdState(next);
                      field.onChange(next);
                    }}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />
          )}
        </div>
      </section>

      {/* 4. Telephony */}
      <section className="space-y-4 rounded-md border p-4">
        <div className="flex items-center gap-1.5">
          <h4 className="text-base font-semibold tracking-tight">Telephony</h4>
          <FieldHelp ariaLabel="About telephony">
            Provider credentials for calls (numbers are on the Basic Info tab)
          </FieldHelp>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="telephony_config_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="frost-text-muted">
                  Provider<span className="text-red-500">*</span>
                </FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select telephony configuration" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {telephonyConfigs.map((config) => (
                      <SelectItem key={config.id} value={config.id}>
                        {getTelephonyProviderConfig(config.provider as TelephonyProvider).name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </section>
    </>
  );
};

export default ConfigurationsSection;
