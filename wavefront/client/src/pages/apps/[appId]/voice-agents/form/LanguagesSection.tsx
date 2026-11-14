import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Textarea } from '@app/components/ui/textarea';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName } from '@app/constants/languages';
import { useFormContext } from 'react-hook-form';
import { MAX_LANGUAGE_PROMPT_CHARS, readLanguagePrompts, withLanguagePrompt } from './language-prompts';
import { VoiceAgentInput } from './voice-agent-form';

const LanguagesSection = ({ isEdit }: { isEdit: boolean }) => {
  const form = useFormContext<VoiceAgentInput>();
  const supported = form.watch('supported_languages') || [];
  // Packs live inside the Advanced tab's conversation_config JSON (one source of truth)
  const configText = form.watch('conversation_config');
  const packs = readLanguagePrompts(configText);

  const setConfigText = (text: string | undefined) => {
    if (text !== undefined && text !== configText) {
      form.setValue('conversation_config', text, { shouldDirty: true });
    }
  };

  return (
    <>
      <FormField
        control={form.control}
        name="supported_languages"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              Supported Languages<span className="text-red-500">*</span>
            </FormLabel>
            <div className="rounded-md border p-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <div key={lang.code} className="flex items-center space-x-2">
                    <Checkbox
                      id={`${isEdit ? 'edit-' : ''}supported-lang-${lang.code}`}
                      checked={field.value?.includes(lang.code)}
                      onCheckedChange={(checked) => {
                        const current = field.value || [];
                        // An unchecked language's pack stays until save, so rechecking it brings the
                        // text back; saving drops it (buildVoiceAgentFields)
                        field.onChange(checked ? [...current, lang.code] : current.filter((l) => l !== lang.code));
                      }}
                    />
                    <label
                      htmlFor={`${isEdit ? 'edit-' : ''}supported-lang-${lang.code}`}
                      className="cursor-pointer text-sm leading-none font-normal peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                    >
                      {getLanguageDisplayName(lang.code)}
                    </label>
                  </div>
                ))}
              </div>
            </div>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="default_language"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              Default Language<span className="text-red-500">*</span>
            </FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select default language" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {SUPPORTED_LANGUAGES.filter((lang) => form.watch('supported_languages')?.includes(lang.code)).map(
                  (lang) => (
                    <SelectItem key={lang.code} value={lang.code}>
                      {getLanguageDisplayName(lang.code)}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />

      {supported.length > 1 && (
        <div className="space-y-3 rounded-md border p-4">
          <div>
            <h4 className="text-sm font-semibold">Advanced: language instructions (optional)</h4>
            <p className="frost-text-muted text-xs">
              Rules and examples for one language only. They are added to the agent&apos;s instructions while the call
              is in that language and swapped on a language switch, which keeps calls fast and prompts small. Keep rules
              for every language in the main prompt.
            </p>
          </div>
          {packs === undefined ? (
            <p className="frost-text-muted text-xs" role="note">
              This agent&apos;s saved conversation settings can&apos;t be read, so these can&apos;t be edited. Use Reset
              to defaults on the Advanced tab to start over.
            </p>
          ) : (
            supported.map((code) => {
              const id = `${isEdit ? 'edit-' : ''}language-prompt-${code}`;
              const text = packs[code] ?? '';
              const tooLong = text.length > MAX_LANGUAGE_PROMPT_CHARS;
              return (
                <div key={code} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={id}>{getLanguageDisplayName(code)} instructions</Label>
                    <span className={tooLong ? 'text-xs text-red-600' : 'frost-text-muted text-xs'}>
                      {text.length.toLocaleString()} / {MAX_LANGUAGE_PROMPT_CHARS.toLocaleString()}
                    </span>
                  </div>
                  <Textarea
                    id={id}
                    rows={3}
                    value={text}
                    onChange={(e) => setConfigText(withLanguagePrompt(configText, code, e.target.value))}
                    className="font-mono text-xs"
                  />
                </div>
              );
            })
          )}
        </div>
      )}
    </>
  );
};

export default LanguagesSection;
