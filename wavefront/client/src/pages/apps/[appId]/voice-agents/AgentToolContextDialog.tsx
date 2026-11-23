import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Switch } from '@app/components/ui/switch';
import { Textarea } from '@app/components/ui/textarea';
import { useSetAgentToolOverrides } from '@app/hooks';
import { toneClass } from '@app/lib/tones';
import { VoiceAgentToolWithAssociation } from '@app/types/tool';
import { Sparkles } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import {
  ArgumentSource,
  argumentSource,
  describeOnCall,
  effectiveMethod,
  fieldLabel,
  parsePromptFields,
  prefetchBlockers,
  readToolContext,
  sourceOption,
  sourceOptions,
  suggestedSource,
  toolArguments,
  ToolContextSettings,
  usableBind,
  writeToolContext,
} from './agent-tool-context';

interface AgentToolContextDialogProps {
  appId: string;
  agentId: string;
  tool: VoiceAgentToolWithAssociation;
  onOpenChange: (open: boolean) => void;
}

const Section: React.FC<{ step: number; title: string; hint: string; children: React.ReactNode }> = ({
  step,
  title,
  hint,
  children,
}) => (
  <section className="space-y-3">
    <div>
      <h4 className="text-sm font-semibold">
        {step}. {title}
      </h4>
      <p className="frost-text-muted text-xs">{hint}</p>
    </div>
    {children}
  </section>
);

/** Per agent↔tool call context: who fills each argument, and reuse / fetch-at-call-start. */
const AgentToolContextDialog: React.FC<AgentToolContextDialogProps> = ({ appId, agentId, tool, onOpenChange }) => {
  const overrides = tool.association.config_overrides;
  const args = useMemo(() => toolArguments(tool), [tool]);
  const method = effectiveMethod(tool, overrides);
  // Saved binds the server ignores (e.g. a whole object argument) are shown, then dropped on save
  const [ignoredBinds] = useState(() => usableBind(args, readToolContext(overrides).bind).ignored);
  const [settings, setSettings] = useState<ToolContextSettings>(() => {
    const saved = readToolContext(overrides);
    return { ...saved, bind: usableBind(args, saved.bind).bind };
  });
  const [promptText, setPromptText] = useState(() => (settings.promptFields ?? []).join('\n'));
  const saveOverrides = useSetAgentToolOverrides(appId, agentId);

  const blockers = prefetchBlockers(args, method, settings);
  const canPrefetch = blockers.length === 0;
  // A prefetch that a later change blocked is shown off and saved off
  const prefetchOn = settings.prefetch && canPrefetch;
  // Prompt fields come from the prefetched result, so they only apply with it
  const promptFields = prefetchOn ? parsePromptFields(promptText) : [];
  const onCall = describeOnCall(method, { ...settings, promptFields }, canPrefetch);
  const fillsPhone = Object.values(settings.bind).includes('caller.phone');

  const setSource = (arg: string, source: ArgumentSource) =>
    setSettings((current) => {
      const bind = { ...current.bind };
      if (source === 'ai') delete bind[arg];
      else bind[arg] = source;
      return { ...current, bind };
    });

  const handleSave = () =>
    saveOverrides.mutate(
      {
        toolId: tool.id,
        configOverrides: writeToolContext(overrides, { ...settings, prefetch: prefetchOn, promptFields }),
      },
      { onSuccess: () => onOpenChange(false) }
    );

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Call context: {tool.display_name}</DialogTitle>
          <DialogDescription>
            Make this tool faster and more reliable on phone calls. Nothing changes until you set something here.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-2">
          <Section
            step={1}
            title="Who fills in each detail?"
            hint="The AI normally fills every detail from the conversation. Details taken from the call itself are always right, and the caller is never asked for them."
          >
            {ignoredBinds.length > 0 && (
              <div className={`rounded-md p-3 text-xs ${toneClass.warning}`} role="note">
                Saved settings for {ignoredBinds.map(fieldLabel).join(', ')} don&apos;t work on calls: only a text
                detail can come from the call, not a whole object. Pick the field inside it below. Saving removes the
                old setting.
              </div>
            )}
            {args.length === 0 ? (
              <div className="frost-text-muted rounded-md border border-dashed p-3 text-sm">
                This tool takes no details.
              </div>
            ) : (
              <div className="space-y-2">
                {args.map((arg) => {
                  const source = argumentSource(settings, arg.name);
                  const suggestion = source === 'ai' ? suggestedSource(arg) : undefined;
                  return (
                    <div
                      key={arg.name}
                      className="border-frost-border flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-start sm:justify-between"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <Label htmlFor={`source-${arg.name}`} className="font-mono text-sm">
                            {fieldLabel(arg.name)}
                          </Label>
                          {arg.required && <Badge className={toneClass.neutral}>required</Badge>}
                        </div>
                        {arg.description && <p className="frost-text-muted mt-1 text-xs">{arg.description}</p>}
                        {suggestion && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="mt-1 h-auto px-0 py-0.5 text-xs"
                            onClick={() => setSource(arg.name, suggestion)}
                          >
                            <Sparkles className="mr-1 h-3 w-3" />
                            Use {sourceOption(suggestion).label.toLowerCase()}
                          </Button>
                        )}
                      </div>
                      <div className="sm:w-64">
                        {!arg.bindable ? (
                          <p className="frost-text-muted text-xs">
                            Always the AI. Only text details can come from the call.
                          </p>
                        ) : (
                          <>
                            <Select
                              value={source}
                              onValueChange={(value) => setSource(arg.name, value as ArgumentSource)}
                            >
                              <SelectTrigger id={`source-${arg.name}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {sourceOptions(source).map((s) => (
                                  <SelectItem key={s.value} value={s.value}>
                                    {s.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <p className="frost-text-muted mt-1 text-xs">{sourceOption(source).example}</p>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>

          <Section
            step={2}
            title="Make it faster"
            hint="Optional. Only for tools that look something up, like a balance or an account status."
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <Label htmlFor="context-read-only">Only reads data</Label>
                <p className="frost-text-muted text-xs">
                  Turn on only if calling this tool never changes anything: it looks up a balance, it doesn&apos;t book
                  a slot. Its answer is then reused if it&apos;s needed again in the same call.
                  {method === 'GET' && ' This tool uses GET, which usually only reads.'}
                </p>
              </div>
              <Switch
                id="context-read-only"
                checked={settings.readOnly}
                onCheckedChange={(readOnly) => setSettings((current) => ({ ...current, readOnly }))}
              />
            </div>

            <div className="flex items-start justify-between gap-4">
              <div>
                <Label htmlFor="context-prefetch">Look it up as the call starts</Label>
                <p className="frost-text-muted text-xs">
                  Runs while the phone rings or the greeting plays, so the answer is ready before the caller asks. It
                  runs on every call, even when nobody asks, so use it for lookups most callers need.
                </p>
              </div>
              <Switch
                id="context-prefetch"
                checked={prefetchOn}
                disabled={!canPrefetch}
                onCheckedChange={(prefetch) => setSettings((current) => ({ ...current, prefetch }))}
              />
            </div>
            {prefetchOn && (
              <div className="space-y-1">
                <Label htmlFor="context-prompt-fields">Give the AI these details up front (optional)</Label>
                <p className="frost-text-muted text-xs">
                  Fields from this tool&apos;s result, one per line, like customer_name or account.amount_due. The AI
                  knows them from the start of the call, so it can answer without calling the tool. Only text and
                  numbers are used.
                </p>
                <Textarea
                  id="context-prompt-fields"
                  rows={3}
                  value={promptText}
                  onChange={(e) => setPromptText(e.target.value)}
                  placeholder={'customer_name\naccount.amount_due'}
                  className="font-mono text-xs"
                />
              </div>
            )}
            {!canPrefetch && (
              <div className={`rounded-md p-3 text-xs ${toneClass.warning}`} role="note">
                <p className="font-medium">To look it up as the call starts:</p>
                <ul className="mt-1 list-disc space-y-1 pl-4">
                  {blockers.map((blocker) => (
                    <li key={blocker}>{blocker}</li>
                  ))}
                </ul>
              </div>
            )}
          </Section>

          <Section step={3} title="On a phone call" hint="What these settings do, in short.">
            <ul className="frost-glass border-frost-border list-disc space-y-1 rounded-md border p-3 pl-7 text-sm">
              {onCall.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            {fillsPhone && (
              <p className="frost-text-muted text-xs">
                Browser test calls have no phone number, so there the AI keeps asking for it.
              </p>
            )}
          </Section>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saveOverrides.isPending}
          >
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} loading={saveOverrides.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default AgentToolContextDialog;
