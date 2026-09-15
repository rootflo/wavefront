import { PiiEntity, PiiEntityGroup } from '@app/api/guardrails-service';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { Check, ChevronDown, ChevronRight, ChevronsUpDown, Search, X } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import { LOOSE_PATTERN_SCORE, PRECISION_TOOLTIPS, PRECISION_WARNINGS } from './adapter-meta';

const GLOBAL_GROUP = 'Global';

interface Props {
  groups: PiiEntityGroup[];
  /**
   * The stored selection, or undefined when the policy has never specified
   * one. Undefined is not the same as empty: it means "whatever the provider
   * defaults to", and is preserved until the admin actually changes something.
   */
  selected: string[] | undefined;
  disabled: boolean;
  onChange: (entities: string[]) => void;
}

/** Only warn about shape-matching when the weakest pattern is genuinely weak. */
const warningFor = (entity: PiiEntity): string | null => {
  if (entity.precision === 'pattern') {
    const score = entity.min_pattern_score;
    if (score !== null && score >= LOOSE_PATTERN_SCORE) return null;
  }
  return PRECISION_WARNINGS[entity.precision] ?? null;
};

const EntityRow: React.FC<{
  entity: PiiEntity;
  checked: boolean;
  disabled: boolean;
  onToggle: (checked: boolean) => void;
}> = ({ entity, checked, disabled, onToggle }) => {
  const warning = warningFor(entity);
  return (
    <label className="flex items-start gap-2.5">
      <Checkbox
        className="mt-0.5"
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onToggle(value === true)}
      />
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-gray-800">{entity.label}</span>
          {warning && (
            <span
              title={PRECISION_TOOLTIPS[entity.precision]}
              className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800"
            >
              {warning}
            </span>
          )}
        </span>
        <span className="mt-0.5 block text-xs text-gray-500">{entity.description}</span>
        {entity.example && <span className="mt-0.5 block font-mono text-[11px] text-gray-400">{entity.example}</span>}
      </span>
    </label>
  );
};

const PiiEntitySelector: React.FC<Props> = ({ groups, selected, disabled, onChange }) => {
  const [search, setSearch] = useState('');
  const [countryPickerOpen, setCountryPickerOpen] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [pickedCountries, setPickedCountries] = useState<string[]>([]);

  const globalGroup = useMemo(() => groups.find((group) => group.group === GLOBAL_GROUP), [groups]);
  const countryGroups = useMemo(() => groups.filter((group) => group.group !== GLOBAL_GROUP), [groups]);

  const defaults = useMemo(
    () => groups.flatMap((group) => group.entities.filter((e) => e.default_selected).map((e) => e.id)),
    [groups]
  );

  // An unconfigured policy shows the provider's defaults ticked. They are not
  // written to the policy until the admin changes something, so a card nobody
  // touches keeps round-tripping as an empty options object.
  const effective = selected ?? defaults;
  const selectedSet = useMemo(() => new Set(effective), [effective]);

  // A country holding selected entities is always shown, whether or not it was
  // picked in this session. Hiding it would leave the policy enforcing
  // identifiers that are invisible on the page.
  useEffect(() => {
    const withSelection = countryGroups
      .filter((group) => group.entities.some((entity) => selectedSet.has(entity.id)))
      .map((group) => group.group);
    if (!withSelection.length) return;
    setPickedCountries((current) => {
      const missing = withSelection.filter((name) => !current.includes(name));
      return missing.length ? [...current, ...missing] : current;
    });
  }, [countryGroups, selectedSet]);

  const query = search.trim().toLowerCase();
  const matches = (entity: PiiEntity) =>
    entity.label.toLowerCase().includes(query) ||
    entity.id.toLowerCase().includes(query) ||
    entity.description.toLowerCase().includes(query);

  const filterGroup = (group: PiiEntityGroup) =>
    query ? { ...group, entities: group.entities.filter(matches) } : group;

  // Global first, then whichever countries have been added. One list, so the
  // sections behave identically - Global just cannot be removed.
  const visibleGroups = useMemo(
    () =>
      [...(globalGroup ? [globalGroup] : []), ...countryGroups.filter((g) => pickedCountries.includes(g.group))]
        .map(filterGroup)
        .filter((group) => group.entities.length > 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [globalGroup, countryGroups, pickedCountries, query]
  );

  // Searching for an identifier whose country has not been added would
  // otherwise be a dead end, so say where the matches are instead.
  const hiddenMatches = useMemo(() => {
    if (!query) return [];
    return countryGroups
      .filter((group) => !pickedCountries.includes(group.group))
      .map((group) => ({ group: group.group, count: group.entities.filter(matches).length }))
      .filter((entry) => entry.count > 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countryGroups, pickedCountries, query]);

  const toggle = (id: string, checked: boolean) => {
    onChange(checked ? [...effective, id] : effective.filter((entity) => entity !== id));
  };

  const selectedCountIn = (group: PiiEntityGroup) =>
    group.entities.filter((entity) => selectedSet.has(entity.id)).length;

  const addCountry = (name: string) => {
    setPickedCountries((current) => (current.includes(name) ? current : [...current, name]));
  };

  /**
   * Dropping a country also unticks its identifiers.
   *
   * Leaving them selected would mean the namespace keeps redacting something
   * the page no longer shows. The chip carries the count, so this is never a
   * silent loss.
   */
  const removeCountry = (name: string) => {
    const group = countryGroups.find((item) => item.group === name);
    if (group) {
      const dropped = new Set(group.entities.map((entity) => entity.id));
      const remaining = effective.filter((entity) => !dropped.has(entity));
      // Only write when something actually changed. Otherwise removing a
      // country that had nothing ticked would turn an untouched policy into an
      // explicit selection, losing the "use the provider defaults" state.
      if (remaining.length !== effective.length) onChange(remaining);
    }
    setPickedCountries((current) => current.filter((item) => item !== name));
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="pr-8">
          <Label className="text-sm font-medium">What to redact</Label>
          <p className="mt-1 text-xs text-gray-500">
            Only the types you select are detected. Anything unselected is passed through untouched.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => onChange(defaults)}
          title="Return to the provider's default set"
        >
          Reset to defaults
        </Button>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            className="pl-9"
            placeholder="Search identifiers, e.g. aadhaar, passport, card"
            value={search}
            disabled={disabled}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Popover open={countryPickerOpen} onOpenChange={setCountryPickerOpen}>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" role="combobox" disabled={disabled} className="shrink-0">
              Add country
              <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-0" align="end">
            <Command>
              <CommandInput placeholder="Search countries..." />
              <CommandList>
                <CommandEmpty>No country matches.</CommandEmpty>
                <CommandGroup>
                  {countryGroups.map((group) => {
                    const isPicked = pickedCountries.includes(group.group);
                    return (
                      <CommandItem
                        key={group.group}
                        value={group.group}
                        onSelect={() => (isPicked ? removeCountry(group.group) : addCountry(group.group))}
                      >
                        <Check className={`mr-2 h-4 w-4 ${isPicked ? 'opacity-100' : 'opacity-0'}`} />
                        <span className="flex-1">{group.group}</span>
                        <span className="text-xs text-gray-400">{group.entities.length}</span>
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {pickedCountries.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {pickedCountries.map((name) => {
            const group = countryGroups.find((item) => item.group === name);
            const count = group ? selectedCountIn(group) : 0;
            return (
              <Badge key={name} variant="secondary" className="gap-1.5">
                {name}
                {count > 0 && <span className="text-[11px] opacity-70">{count} on</span>}
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => removeCountry(name)}
                  title={count > 0 ? `Remove ${name} and untick its ${count} selected types` : `Remove ${name}`}
                  className="cursor-pointer hover:text-red-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}

      {effective.length === 0 && (
        <p className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
          Nothing is selected, so this provider would detect nothing while still appearing to be on. Select at least one
          type, or switch the provider off.
        </p>
      )}

      <div className="mt-3 flex flex-col divide-y divide-gray-100 rounded-md border border-gray-200">
        {visibleGroups.map((group) => {
          const open = query ? true : (expanded[group.group] ?? false);
          const count = selectedCountIn(group);
          return (
            <div key={group.group}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => setExpanded((current) => ({ ...current, [group.group]: !current[group.group] }))}
                className="flex w-full items-center justify-between px-3 py-2.5 text-left hover:bg-gray-50 disabled:cursor-not-allowed"
              >
                <span className="flex items-center gap-2 text-sm font-medium text-gray-800">
                  {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  {group.group}
                  <span className="text-xs font-normal text-gray-500">({group.entities.length})</span>
                </span>
                {count > 0 && (
                  <span className="rounded bg-gray-900 px-2 py-0.5 text-xs font-medium text-white">{count}</span>
                )}
              </button>

              {open && (
                <div className="flex flex-col gap-3 px-3 pt-1 pb-3">
                  {group.entities.map((entity) => (
                    <EntityRow
                      key={entity.id}
                      entity={entity}
                      checked={selectedSet.has(entity.id)}
                      disabled={disabled}
                      onToggle={(checked) => toggle(entity.id, checked)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {visibleGroups.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-gray-500">
            {query ? `No identifiers match "${search}".` : 'No identifier groups available.'}
          </p>
        )}
      </div>

      {hiddenMatches.length > 0 && (
        <p className="mt-3 rounded-md border border-dashed border-gray-300 bg-gray-50 p-3 text-xs text-gray-600">
          Also found in countries you have not added:{' '}
          {hiddenMatches.map((entry, index) => (
            <React.Fragment key={entry.group}>
              {index > 0 && ', '}
              <button
                type="button"
                disabled={disabled}
                onClick={() => addCountry(entry.group)}
                className="cursor-pointer font-medium text-gray-900 underline underline-offset-2"
              >
                {entry.group} ({entry.count})
              </button>
            </React.Fragment>
          ))}
        </p>
      )}
    </div>
  );
};

export default PiiEntitySelector;
