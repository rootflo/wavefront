import { Check, ChevronsUpDown, Pencil } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@app/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import { Input } from '@app/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { findModelPreset, getModelGroups, type ModelTag } from '@app/config/llm-models';
import type { InferenceEngineType } from '@app/config/llm-providers';
import { cn } from '@app/lib/utils';

const TAG_STYLES: Record<ModelTag, string> = {
  voice: 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300',
  fast: 'bg-sky-400/15 text-sky-800 dark:text-sky-300',
  reasoning: 'bg-violet-400/15 text-violet-800 dark:text-violet-300',
  preview: 'bg-amber-400/15 text-amber-800 dark:text-amber-300',
  legacy: 'frost-text-muted bg-frost-glass-strong',
};

const TAG_LABELS: Record<ModelTag, string> = {
  voice: 'Voice',
  fast: 'Fast',
  reasoning: 'Reasoning',
  preview: 'Preview',
  legacy: 'Older',
};

export function ModelTags({ tags, className }: { tags?: ModelTag[]; className?: string }) {
  if (!tags?.length) return null;
  return (
    <span className={cn('flex shrink-0 flex-wrap gap-1', className)}>
      {tags.map((tag) => (
        <span key={tag} className={cn('rounded-full px-1.5 py-0.5 text-[10px] font-medium', TAG_STYLES[tag])}>
          {TAG_LABELS[tag]}
        </span>
      ))}
    </span>
  );
}

interface ModelSelectProps {
  provider: InferenceEngineType;
  value: string;
  onChange: (modelId: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Searchable picker over the provider's popular models. Any other ID can be
 * typed into the search and used as is (new models, Azure deployment names,
 * self-hosted models).
 */
export function ModelSelect({ provider, value, onChange, disabled, placeholder }: ModelSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const groups = useMemo(() => getModelGroups(provider), [provider]);
  const preset = findModelPreset(provider, value);
  const exactPreset = preset?.id === value.trim().toLowerCase() ? preset : null;
  const typed = search.trim();
  const typedIsListed = groups.some((g) => g.models.some((m) => m.id === typed.toLowerCase()));

  const choose = (modelId: string) => {
    onChange(modelId);
    setSearch('');
    setOpen(false);
  };

  // Self-hosted providers have no catalog: the model is whatever the server serves.
  if (!groups.length) {
    return (
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder || 'Model name'}
      />
    );
  }

  return (
    <Popover modal open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="h-auto min-h-9 w-full justify-between py-1.5 font-normal"
        >
          {value ? (
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate">{exactPreset ? exactPreset.label : value}</span>
              {exactPreset ? (
                <span className="frost-text-muted truncate font-mono text-xs">{exactPreset.id}</span>
              ) : (
                preset && <span className="frost-text-muted truncate text-xs">settings of {preset.label}</span>
              )}
            </span>
          ) : (
            <span className="frost-text-muted">{placeholder || 'Select a model'}</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-(--radix-popover-trigger-width) min-w-80 p-0"
        align="start"
        onWheel={(e) => e.stopPropagation()}
      >
        <Command>
          <CommandInput placeholder="Search, or type a model ID..." value={search} onValueChange={setSearch} />
          <CommandList className="max-h-80 overflow-y-auto overscroll-contain">
            <CommandEmpty>{typed ? 'No listed model matches.' : 'Type the model ID to use.'}</CommandEmpty>
            {typed && !typedIsListed && (
              <CommandGroup heading="Custom">
                <CommandItem value={`__custom__ ${typed}`} onSelect={() => choose(typed)}>
                  <Pencil className="mr-2 h-4 w-4" />
                  <span className="truncate">
                    Use <span className="font-mono">{typed}</span>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
            {groups.map((group) => (
              <CommandGroup key={group.label} heading={group.label}>
                {group.models.map((model) => (
                  <CommandItem
                    key={model.id}
                    value={`${model.label} ${model.id} ${model.description}`}
                    onSelect={() => choose(model.id)}
                  >
                    <Check
                      className={cn(
                        'mr-2 h-4 w-4 shrink-0',
                        exactPreset?.id === model.id ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="flex items-center gap-2">
                        <span className="truncate">{model.label}</span>
                        <ModelTags tags={model.tags} />
                      </span>
                      <span className="frost-text-muted truncate text-xs">
                        <span className="font-mono">{model.id}</span> · {model.description}
                      </span>
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
