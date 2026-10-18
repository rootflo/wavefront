import { useEffect, useMemo } from 'react';

import FieldHelp from '@app/components/FieldHelp';
import { VoiceIdSelect } from '@app/components/VoiceIdSelect';
import { Label } from '@app/components/ui/label';
import { Switch } from '@app/components/ui/switch';
import { getLanguageDisplayName } from '@app/constants/languages';
import { getDefaultTtsVoiceId, getTtsVoiceOptions, isTtsVoiceIdValid } from '@app/config/tts-voice-catalogs';

interface VoiceIdsSectionProps {
  provider: string | undefined;
  model: string | undefined;
  languages: string[];
  voiceIds: Record<string, string>;
  customizePerLanguage: boolean;
  onCustomizePerLanguageChange: (enabled: boolean) => void;
  onChange: (voiceIds: Record<string, string>) => void;
}

/**
 * Default voice applies to every language; optional per-language overrides.
 */
export function VoiceIdsSection({
  provider,
  model,
  languages,
  voiceIds,
  customizePerLanguage,
  onCustomizePerLanguageChange,
  onChange,
}: VoiceIdsSectionProps) {
  const sharedVoiceId = useMemo(() => {
    if (languages.length === 0) return '';
    const values = languages.map((lang) => voiceIds[lang] || '');
    const first = values[0] || '';
    return values.every((value) => value === first) ? first : first;
  }, [languages, voiceIds]);

  const applyToAll = (voiceId: string) => {
    const next: Record<string, string> = {};
    languages.forEach((lang) => {
      next[lang] = voiceId;
    });
    onChange(next);
  };

  const setLanguageVoice = (langCode: string, voiceId: string) => {
    onChange({ ...voiceIds, [langCode]: voiceId });
  };

  const handleCustomizeToggle = (enabled: boolean) => {
    onCustomizePerLanguageChange(enabled);
    if (!enabled && sharedVoiceId) {
      applyToAll(sharedVoiceId);
    }
  };

  // Auto-select a valid default voice when provider/model changes or voices are empty/invalid
  useEffect(() => {
    if (!provider || languages.length === 0) return;
    if (getTtsVoiceOptions(provider, model).length === 0) return;

    const next: Record<string, string> = { ...voiceIds };
    let changed = false;

    if (!customizePerLanguage) {
      const current = languages.map((lang) => voiceIds[lang] || '').find(Boolean) || '';
      const valid = isTtsVoiceIdValid(provider, model, current);
      const defaultId = valid ? current : getDefaultTtsVoiceId(provider, model);
      if (!defaultId) return;

      languages.forEach((lang) => {
        if (next[lang] !== defaultId) {
          next[lang] = defaultId;
          changed = true;
        }
      });
    } else {
      languages.forEach((lang) => {
        const current = voiceIds[lang] || '';
        if (isTtsVoiceIdValid(provider, model, current, lang)) return;
        const defaultId = getDefaultTtsVoiceId(provider, model, lang);
        if (defaultId && next[lang] !== defaultId) {
          next[lang] = defaultId;
          changed = true;
        }
      });
    }

    if (changed) onChange(next);
    // Only react to catalog context / language list — not every voiceIds keystroke
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, model, languages.join(','), customizePerLanguage]);

  return (
    <div className="space-y-3 border-t pt-4">
      <div className="flex items-center gap-1.5">
        <h5 className="text-sm font-semibold tracking-tight">
          Voices<span className="text-red-500">*</span>
        </h5>
        <FieldHelp ariaLabel="About voices">
          Pick one voice for all languages, or override individual languages.
        </FieldHelp>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 space-y-2">
          <Label className="frost-text-muted text-sm font-medium">Default voice</Label>
          <VoiceIdSelect
            provider={provider}
            model={model}
            placeholder="Select a voice for all languages"
            value={sharedVoiceId}
            onChange={applyToAll}
            className="w-full"
          />
        </div>

        {languages.length > 1 && (
          <div className="flex shrink-0 items-center gap-3 rounded-md border px-3 py-2 sm:h-9 sm:border-0 sm:px-0 sm:py-0">
            <Label
              htmlFor="customize-voices"
              className="frost-text-muted cursor-pointer text-sm font-medium whitespace-nowrap"
            >
              Override per language
            </Label>
            <Switch id="customize-voices" checked={customizePerLanguage} onCheckedChange={handleCustomizeToggle} />
          </div>
        )}
      </div>

      {customizePerLanguage && (
        <div className="grid grid-cols-2 gap-3">
          {languages.map((langCode) => (
            <div key={langCode} className="flex min-w-0 flex-col gap-1.5">
              <Label className="frost-text-muted text-sm font-medium">{getLanguageDisplayName(langCode)}</Label>
              <VoiceIdSelect
                provider={provider}
                model={model}
                languageCode={langCode}
                placeholder={`Voice for ${getLanguageDisplayName(langCode)}`}
                value={voiceIds[langCode] || ''}
                onChange={(nextValue) => setLanguageVoice(langCode, nextValue)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
