import { Button } from '@app/components/ui/button';
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import { Control, FieldValues, Path, PathValue, UseFormReturn } from 'react-hook-form';
import { CONVERSATION_CONFIG_DOCS, ConversationConfig, DEFAULT_EDITOR_TEXT, withDefaults } from './conversation-config';

interface ConversationConfigFieldProps<T extends FieldValues> {
  form: UseFormReturn<T>;
  /** Form field holding the editor text. */
  name: Path<T>;
}

const parseObject = (text: string): ConversationConfig | null => {
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? (parsed as ConversationConfig)
      : null;
  } catch {
    return null;
  }
};

/** The Advanced tab: JSON editor pre-filled with the defaults, plus a reference for every option. */
function ConversationConfigField<T extends FieldValues>({ form, name }: ConversationConfigFieldProps<T>) {
  const setText = (text: string) =>
    form.setValue(name, text as PathValue<T, Path<T>>, { shouldDirty: true, shouldValidate: true });

  const addMissingDefaults = () => {
    const current = parseObject((form.getValues(name) as string | undefined) ?? '{}');
    if (!current) {
      setText(DEFAULT_EDITOR_TEXT);
      return;
    }
    setText(JSON.stringify(withDefaults(current), null, 2));
  };

  return (
    <>
      <FormField
        control={form.control as Control<T>}
        name={name}
        render={({ field }) => (
          <FormItem>
            <div className="flex items-center justify-between gap-2">
              <FormLabel>Conversation Configuration</FormLabel>
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" onClick={addMissingDefaults}>
                  Add missing defaults
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setText(DEFAULT_EDITOR_TEXT)}>
                  Reset to defaults
                </Button>
              </div>
            </div>
            <p className="frost-text-muted text-xs">
              This is what a bot with no configuration does. Change a value to tune this bot; leave it untouched to keep
              following the defaults. Keys you remove fall back to their default.
            </p>
            <FormControl>
              <div className="w-full min-w-0">
                <CodeMirror
                  value={field.value || DEFAULT_EDITOR_TEXT}
                  onChange={field.onChange}
                  theme="dark"
                  height="340px"
                  width="100%"
                  maxWidth="100%"
                  className="w-full min-w-0"
                  extensions={[langs.json(), ...popupCodeMirrorExtensions]}
                  placeholder={DEFAULT_EDITOR_TEXT}
                />
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="space-y-6 pt-2">
        <div>
          <h3 className="text-sm font-medium">What each option does</h3>
          <p className="frost-text-muted text-xs">
            All values are optional. Times are in milliseconds (1000 ms = 1 second). Values outside the range are
            clamped to it, and an invalid value is ignored in favour of its default.
          </p>
        </div>

        {CONVERSATION_CONFIG_DOCS.map((section) => (
          <div key={section.section} className="space-y-2">
            <div>
              <h4 className="text-sm font-medium">
                {section.title} <code className="frost-text-muted text-xs font-normal">{section.section}</code>
              </h4>
              <p className="frost-text-muted text-xs">{section.summary}</p>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[210px]">Option</TableHead>
                  <TableHead className="w-[90px]">Default</TableHead>
                  <TableHead className="w-[130px]">Allowed</TableHead>
                  <TableHead>What it does</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {section.options.map((option) => (
                  <TableRow key={option.key}>
                    <TableCell className="align-top font-mono text-xs">{option.key}</TableCell>
                    <TableCell className="align-top text-xs">{option.defaultValue}</TableCell>
                    <TableCell className="align-top text-xs">{option.range}</TableCell>
                    <TableCell className="align-top text-xs whitespace-normal">{option.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}

        <div className="space-y-2">
          <h4 className="text-sm font-medium">Examples</h4>
          <ul className="frost-text-muted list-disc space-y-1 pl-5 text-xs">
            <li>
              <b>Bot must finish what it says:</b> set <code>barge_in</code> to false. Nothing the user says over the
              bot interrupts it.
            </li>
            <li>
              <b>Welcome message must play fully:</b> set <code>mute_until_first_bot_complete</code> to true. Users can
              still interrupt the bot after the welcome.
            </li>
            <li>
              <b>Fewer accidental interruptions:</b> keep <code>barge_in</code> true and set{' '}
              <code>barge_in_min_words</code> to 2. The bot then stops only after two words are heard, not on any sound.
            </li>
            <li>
              <b>Noisy phone line:</b> raise <code>vad_confidence</code> and <code>vad_min_volume</code>, and set{' '}
              <code>barge_in_min_words</code> to 3 (or turn barge-in off).
            </li>
            <li>
              <b>Bot talks over users who pause:</b> raise <code>end_of_turn_timeout_ms</code>.
            </li>
            <li>
              <b>Bot interrupts itself on speakers:</b> raise <code>barge_in_min_words</code> to 2 or more, or turn
              barge-in off (echo can sound like the user).
            </li>
            <li>
              <b>Snappier replies:</b> lower <code>end_of_turn_timeout_ms</code> to about 1500.
            </li>
          </ul>
        </div>
      </div>
    </>
  );
}

export default ConversationConfigField;
