import { useMemo, useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';

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
import { getTtsVoiceLabel, getTtsVoiceOptions } from '@app/config/tts-voice-catalogs';
import { cn } from '@app/lib/utils';

interface VoiceIdSelectProps {
  provider: string | undefined;
  model: string | undefined;
  /** When omitted, shows the full provider catalog (for default-all-languages). */
  languageCode?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Searchable voice/speaker picker when a catalog exists for the TTS provider.
 * Stores the voice ID but displays the friendly name when selected.
 * Falls back to free-text input for account-specific IDs (e.g. ElevenLabs).
 */
export function VoiceIdSelect({
  provider,
  model,
  languageCode,
  value,
  onChange,
  placeholder,
  className,
}: VoiceIdSelectProps) {
  const [open, setOpen] = useState(false);
  const options = useMemo(() => getTtsVoiceOptions(provider, model, languageCode), [provider, model, languageCode]);

  const displayLabel = useMemo(() => {
    if (!value) return placeholder || 'Select voice';
    return getTtsVoiceLabel(provider, model, value) || value;
  }, [provider, model, value, placeholder]);

  if (options.length === 0) {
    return (
      <Input
        placeholder={placeholder || 'Voice ID'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn('flex-1', className)}
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
          className={cn('w-full justify-between font-normal', className)}
        >
          <span className="truncate">{displayLabel}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[var(--radix-popover-trigger-width)] p-0"
        align="start"
        onWheel={(e) => e.stopPropagation()}
      >
        <Command>
          <CommandInput placeholder="Search voices..." />
          <CommandList className="max-h-60 overflow-y-auto overscroll-contain">
            <CommandEmpty>No voice found.</CommandEmpty>
            <CommandGroup>
              {options.map((option) => (
                <CommandItem
                  key={option.value}
                  value={`${option.label} ${option.value}`}
                  onSelect={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                >
                  <Check className={cn('mr-2 h-4 w-4', value === option.value ? 'opacity-100' : 'opacity-0')} />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate">{option.label}</span>
                    {option.label !== option.value && (
                      <span className="text-muted-foreground truncate text-xs">{option.value}</span>
                    )}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
