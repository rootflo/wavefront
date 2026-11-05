import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName } from '@app/constants/languages';
import { useFormContext } from 'react-hook-form';
import { VoiceAgentInput } from './voice-agent-form';

const LanguagesSection = ({ isEdit }: { isEdit: boolean }) => {
  const form = useFormContext<VoiceAgentInput>();

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
                        if (checked) {
                          field.onChange([...current, lang.code]);
                        } else {
                          field.onChange(current.filter((l) => l !== lang.code));
                        }
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
    </>
  );
};

export default LanguagesSection;
