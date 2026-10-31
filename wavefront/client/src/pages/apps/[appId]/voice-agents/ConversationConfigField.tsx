import FieldHelp from '@app/components/FieldHelp';
import { Button } from '@app/components/ui/button';
import { FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import { Textarea } from '@app/components/ui/textarea';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName, getLanguageName } from '@app/constants/languages';
import { cn } from '@app/lib/utils';
import { ChevronDown, RotateCcw, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Control, FieldValues, Path, PathValue, UseFormReturn } from 'react-hook-form';
import {
  CONVERSATION_CONFIG_DOCS,
  ConfigOptionDoc,
  ConfigSectionDoc,
  ConversationConfig,
  DEFAULT_CONVERSATION_CONFIG,
  DEFAULT_EDITOR_TEXT,
  isDeepEqual,
  isOutOfRange,
  isPlainObject,
  splitSectionOptions,
} from './conversation-config';

type PhraseMap = Record<string, string[]>;

interface ConversationConfigFieldProps<T extends FieldValues> {
  form: UseFormReturn<T>;
  /** Form field holding the config as JSON text. */
  name: Path<T>;
  /** Whether the agent has a welcome message; without one the welcome options do nothing. */
  hasWelcomeMessage: boolean;
  /** Whether the agent supports more than one language; without that the language options do nothing. */
  isMultiLanguage: boolean;
}

const parseObject = (text: string): ConversationConfig | null => {
  try {
    const parsed: unknown = JSON.parse(text);
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const sectionOf = (config: ConversationConfig, section: string): Record<string, unknown> =>
  isPlainObject(config[section]) ? (config[section] as Record<string, unknown>) : {};

const defaultOf = (section: string, key: string): unknown =>
  (DEFAULT_CONVERSATION_CONFIG as Record<string, Record<string, unknown>>)[section]?.[key];

/** Set to something other than its default (the defaults themselves are written out in a new config). */
const isChanged = (value: unknown, defaultValue: unknown) => value !== undefined && !isDeepEqual(value, defaultValue);

/** The Advanced tab: a form over the conversation config, starting from the defaults. */
function ConversationConfigField<T extends FieldValues>({
  form,
  name,
  hasWelcomeMessage,
  isMultiLanguage,
}: ConversationConfigFieldProps<T>) {
  // An empty field means "no config": every option follows its default.
  const readConfig = () => parseObject((form.getValues(name) as string | undefined) || '{}');
  const config = parseObject((form.watch(name) as string | undefined) || '{}') ?? {};

  const setText = (text: string) =>
    form.setValue(name, text as PathValue<T, Path<T>>, { shouldDirty: true, shouldValidate: true });

  const setConfig = (next: ConversationConfig) => setText(JSON.stringify(next, null, 2));

  /** Sets one option; `undefined` removes it so it falls back to its default. */
  const setOption = (section: string, key: string, value: unknown) => {
    const current = readConfig() ?? {};
    const values = { ...sectionOf(current, section) };
    if (value === undefined) delete values[key];
    else values[key] = value;
    const next = { ...current };
    if (Object.keys(values).length > 0) next[section] = values;
    else delete next[section];
    setConfig(next);
  };

  return (
    <FormField
      control={form.control as Control<T>}
      name={name}
      render={() => (
        <FormItem className="space-y-4">
          <div className="flex items-center justify-between gap-2">
            <FormLabel>Conversation Configuration</FormLabel>
            <Button type="button" variant="outline" size="sm" onClick={() => setText(DEFAULT_EDITOR_TEXT)}>
              Reset to defaults
            </Button>
          </div>
          <p className="frost-text-muted text-xs">
            These settings start from what a bot with no configuration does. Change a value to tune this bot; options
            you reset to default follow the service default. Times are in milliseconds (1000 ms = 1 second), and values
            outside an option&apos;s range are clamped to it. The Guide tab explains every option, with examples.
          </p>

          {CONVERSATION_CONFIG_DOCS.map((section) => (
            <ConfigSection
              key={section.section}
              doc={section}
              values={sectionOf(config, section.section)}
              hasWelcomeMessage={hasWelcomeMessage}
              isMultiLanguage={isMultiLanguage}
              onChange={(key, value) => setOption(section.section, key, value)}
            />
          ))}

          <FormMessage />
        </FormItem>
      )}
    />
  );
}

interface ConfigSectionProps {
  doc: ConfigSectionDoc;
  values: Record<string, unknown>;
  hasWelcomeMessage: boolean;
  isMultiLanguage: boolean;
  onChange: (key: string, value: unknown) => void;
}

function ConfigSection({ doc, values, hasWelcomeMessage, isMultiLanguage, onChange }: ConfigSectionProps) {
  const [open, setOpen] = useState(false);
  const effective = (key: string) => values[key] ?? defaultOf(doc.section, key);

  /** Why an option has no effect with the current values, if it doesn't. */
  const inactiveReason = (option: ConfigOptionDoc): string | undefined => {
    if (option.requires && effective(option.requires) !== true) {
      const required = doc.options.find((o) => o.key === option.requires);
      return `Turn on "${required?.label ?? option.requires}" to use this.`;
    }
    if (option.requiresPositive && !(Number(effective(option.requiresPositive)) > 0)) {
      const required = doc.options.find((o) => o.key === option.requiresPositive);
      return `Set "${required?.label ?? option.requiresPositive}" above 0 to use this.`;
    }
    if (option.key === 'mute_until_first_bot_complete') {
      if (!hasWelcomeMessage) return 'Needs a welcome message (Behavior tab).';
      if (effective('barge_in') === false) return 'Barge-in is off, so the welcome already plays fully.';
    }
    if (doc.section === 'language_switch' && !isMultiLanguage) {
      return 'Needs more than one supported language (Languages tab).';
    }
    if (
      option.key === 'transcript_turn_start' &&
      effective('barge_in') !== false &&
      Number(effective('barge_in_min_words')) > 0
    ) {
      return 'Words needed to interrupt is above 0, so transcripts already start turns.';
    }
    return undefined;
  };

  const renderOption = (option: ConfigOptionDoc) => (
    <ConfigOption
      key={option.key}
      id={`conversation-${doc.section}-${option.key}`}
      option={option}
      value={values[option.key]}
      defaultValue={defaultOf(doc.section, option.key)}
      inactiveReason={inactiveReason(option)}
      onChange={(value) => onChange(option.key, value)}
    />
  );

  const { toggles, settings } = splitSectionOptions(doc.options);
  const settingsChanged = settings.filter((option) =>
    isChanged(values[option.key], defaultOf(doc.section, option.key))
  ).length;

  return (
    <section className="frost-glass border-frost-border space-y-4 rounded-lg border p-4">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full cursor-pointer items-start justify-between gap-3 text-left"
        aria-expanded={open}
      >
        <div>
          <h4 className="text-sm font-medium">{doc.title}</h4>
          <p className="frost-text-muted text-xs">{doc.summary}</p>
        </div>
        <span className="frost-text-muted flex shrink-0 items-center gap-1 text-xs">
          {!open && settingsChanged > 0 && `${settingsChanged} changed ·`}
          {settings.length > 0 && (open ? 'Hide settings' : 'Settings')}
          <ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} />
        </span>
      </button>
      <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">{toggles.map(renderOption)}</div>
      {open && settings.length > 0 && (
        <div className="border-frost-border grid gap-x-6 gap-y-5 border-t pt-4 sm:grid-cols-2">
          {settings.map(renderOption)}
        </div>
      )}
    </section>
  );
}

interface ConfigOptionProps {
  id: string;
  option: ConfigOptionDoc;
  /** The value set on this bot; `undefined` follows the default. */
  value: unknown;
  defaultValue: unknown;
  inactiveReason?: string;
  onChange: (value: unknown) => void;
}

function ConfigOption({ id, option, value, defaultValue, inactiveReason, onChange }: ConfigOptionProps) {
  const isSet = isChanged(value, defaultValue);
  const disabled = !!inactiveReason;
  const outOfRange = isOutOfRange(option, value);

  return (
    <div className={cn('flex flex-col gap-2', option.kind === 'phrases' && 'sm:col-span-2')}>
      <div className="flex min-h-5 items-center justify-between gap-2">
        <label
          htmlFor={id}
          className={cn('frost-text flex items-center gap-1.5 text-sm font-medium', disabled && 'opacity-60')}
        >
          {option.label}
          <FieldHelp ariaLabel={`About ${option.label}`}>{option.description}</FieldHelp>
        </label>
        {isSet && (
          <button
            type="button"
            onClick={() => onChange(undefined)}
            className="frost-text-muted hover:text-frost-text flex cursor-pointer items-center gap-1 text-xs"
            aria-label={`Reset ${option.label} to default`}
          >
            <RotateCcw className="h-3 w-3" />
            Default
          </button>
        )}
      </div>

      {option.kind === 'boolean' && (
        <div className="flex h-9 items-center gap-2">
          <Switch id={id} checked={(value ?? defaultValue) === true} onCheckedChange={onChange} disabled={disabled} />
          <span className={cn('frost-text text-sm', disabled && 'opacity-60')}>
            {(value ?? defaultValue) === true ? 'On' : 'Off'}
            {!isSet && <span className="frost-text-muted"> (default)</span>}
          </span>
        </div>
      )}

      {option.kind === 'number' && (
        <Input
          id={id}
          type="number"
          value={typeof value === 'number' ? value : ''}
          onChange={(e) => {
            // Empty or non-finite input (e.g. 1e999) falls back to the default
            const parsed = e.target.value === '' ? NaN : Number(e.target.value);
            onChange(Number.isFinite(parsed) ? parsed : undefined);
          }}
          min={option.min}
          max={option.max}
          step={option.step}
          placeholder={`Default (${option.defaultValue})`}
          disabled={disabled}
        />
      )}

      {option.kind === 'text' && (
        <Input
          id={id}
          type="text"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value || undefined)}
          placeholder={typeof defaultValue === 'string' ? defaultValue : 'Default'}
          disabled={disabled}
        />
      )}

      {option.kind === 'phrases' && (
        <PhrasesInput
          id={id}
          value={isPlainObject(value) ? (value as PhraseMap) : {}}
          builtIn={option.builtInPhrases ?? {}}
          noun={option.phraseNoun}
          keepEmpty={option.keepEmpty}
          note={option.phrasesNote}
          onChange={onChange}
          disabled={disabled}
        />
      )}

      {inactiveReason ? (
        <p className="frost-text-muted text-xs">{inactiveReason}</p>
      ) : outOfRange ? (
        <p className="text-xs text-amber-500">Outside {option.range}; it will be clamped to that range.</p>
      ) : (
        option.kind === 'number' && <p className="frost-text-subtle text-xs">Range: {option.range}</p>
      )}
    </div>
  );
}

interface PhrasesInputProps {
  id: string;
  value: PhraseMap;
  builtIn: PhraseMap;
  noun?: { one: string; many: string };
  keepEmpty?: boolean;
  note?: string;
  onChange: (value: PhraseMap | undefined) => void;
  disabled?: boolean;
}

/** Custom phrases per chosen language; every other language keeps the built-in phrases shown below. */
export function PhrasesInput({
  id,
  value,
  builtIn,
  noun = { one: 'phrase', many: 'phrases' },
  keepEmpty = false,
  note = 'Other languages use the English phrases (yours if set, otherwise the built-in ones).',
  onChange,
  disabled,
}: PhrasesInputProps) {
  // Languages added here but not given phrases yet stay listed until removed
  const [added, setAdded] = useState<string[]>([]);
  const languages = [...Object.keys(value), ...added.filter((language) => !(language in value))];
  const addable = SUPPORTED_LANGUAGES.filter((language) => !languages.includes(language.code));
  const builtInOnly = Object.keys(builtIn).filter((language) => !languages.includes(language));

  const setLanguage = (language: string, phrases: string[]) => {
    const next = { ...value };
    if (phrases.length > 0 || keepEmpty) next[language] = phrases;
    else delete next[language];
    onChange(Object.keys(next).length > 0 ? next : undefined);
  };

  const addLanguage = (language: string) => {
    setAdded((current) => [...current, language]);
    // Start from the built-in phrases so they can be edited rather than retyped
    if (builtIn[language]) setLanguage(language, builtIn[language]);
  };

  const removeLanguage = (language: string) => {
    setAdded((current) => current.filter((l) => l !== language));
    const next = { ...value };
    delete next[language];
    onChange(Object.keys(next).length > 0 ? next : undefined);
  };

  return (
    <div id={id} className="space-y-3">
      {languages.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {languages.map((language) => (
            <div key={language} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className={cn('frost-text text-xs font-medium', disabled && 'opacity-60')}>
                  {getLanguageDisplayName(language)}
                </span>
                <button
                  type="button"
                  onClick={() => removeLanguage(language)}
                  className="frost-text-muted hover:text-frost-text flex cursor-pointer items-center gap-1 text-xs"
                  aria-label={`Remove ${getLanguageName(language)} ${noun.many}`}
                >
                  <X className="h-3 w-3" />
                  {builtIn[language] ? 'Use built-in' : 'Remove'}
                </button>
              </div>
              <PhraseLines
                value={Array.isArray(value[language]) ? value[language] : []}
                placeholder={
                  keepEmpty && Array.isArray(value[language]) && value[language].length === 0
                    ? `No ${noun.many}: only the language name on its own`
                    : (builtIn[language]?.join('\n') ?? `One ${noun.one} per line`)
                }
                onChange={(phrases) => setLanguage(language, phrases)}
                disabled={disabled}
              />
            </div>
          ))}
        </div>
      )}

      <Select value="" onValueChange={addLanguage} disabled={disabled}>
        <SelectTrigger className="w-full sm:w-64">
          <SelectValue placeholder={`Add ${noun.many} for a language`} />
        </SelectTrigger>
        <SelectContent>
          {addable.map((language) => (
            <SelectItem key={language.code} value={language.code}>
              {getLanguageDisplayName(language.code)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {builtInOnly.length > 0 && (
        <div className={cn('space-y-1', disabled && 'opacity-60')}>
          <p className="frost-text-muted text-xs">Built-in {noun.many}, used for languages you don&apos;t customise:</p>
          <ul className="frost-text-muted space-y-0.5 text-xs">
            {builtInOnly.map((language) => (
              <li key={language}>
                <span className="frost-text font-medium">{getLanguageName(language)}:</span>{' '}
                {builtIn[language].join(' · ')}
              </li>
            ))}
          </ul>
          <p className="frost-text-subtle text-xs">{note}</p>
        </div>
      )}
    </div>
  );
}

interface PhraseLinesProps {
  value: string[];
  placeholder: string;
  onChange: (phrases: string[]) => void;
  disabled?: boolean;
}

const toPhrases = (text: string) =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

function PhraseLines({ value, placeholder, onChange, disabled }: PhraseLinesProps) {
  // Keep the raw text so blank lines survive while typing; resync when the value changes elsewhere (e.g. reset).
  const [text, setText] = useState(() => value.join('\n'));
  useEffect(() => {
    setText((current) => (isDeepEqual(toPhrases(current), value) ? current : value.join('\n')));
  }, [value]);

  return (
    <Textarea
      rows={4}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        onChange(toPhrases(e.target.value));
      }}
      placeholder={placeholder}
      disabled={disabled}
    />
  );
}

export default ConversationConfigField;
