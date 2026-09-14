import { Badge } from '@app/components/ui/badge';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { cn } from '@app/lib/utils';
import { Check, ChevronDown, X } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';

const identity = (id: string) => id;

interface MultiSelectProps<T> {
  items: T[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  getId: (item: T) => string;
  getLabel: (item: T) => string;
  getSearchValue?: (item: T) => string;
  normalizeId?: (id: string) => string;
  placeholder?: string;
  searchPlaceholder?: string;
  loading?: boolean;
  loadingLabel?: string;
  emptyLabel?: string;
  disabled?: boolean;
  showSelectAll?: boolean;
  selectedGroupHeading?: string;
  allItemsGroupHeading?: string;
  selectedCountLabel?: (count: number) => string;
}

const matchesSearch = (value: string, search: string) => value.toLowerCase().includes(search.trim().toLowerCase());

function MultiSelect<T>({
  items,
  selectedIds,
  onChange,
  getId,
  getLabel,
  getSearchValue,
  normalizeId = identity,
  placeholder = 'Select items',
  searchPlaceholder = 'Search...',
  loading = false,
  loadingLabel = 'Loading...',
  emptyLabel = 'No items found.',
  disabled = false,
  showSelectAll = false,
  selectedGroupHeading = 'Selected',
  allItemsGroupHeading = 'All items',
  selectedCountLabel = (count) => `${count} selected`,
}: MultiSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const selectedIdsRef = useRef(selectedIds);
  selectedIdsRef.current = selectedIds;

  const getItemSearchValue = (item: T) => getSearchValue?.(item) ?? getLabel(item);

  const sortedItems = useMemo(
    () => [...items].sort((a, b) => getLabel(a).localeCompare(getLabel(b), undefined, { sensitivity: 'base' })),
    [items, getLabel]
  );

  const isIdSelected = (id: string, ids: string[] = selectedIdsRef.current) =>
    ids.some((selectedId) => normalizeId(selectedId) === normalizeId(id));

  const emitChange = (next: string[]) => {
    selectedIdsRef.current = next;
    onChange(next);
  };

  const toggleItem = (id: string) => {
    const prev = selectedIdsRef.current;
    emitChange(
      isIdSelected(id, prev) ? prev.filter((selectedId) => normalizeId(selectedId) !== normalizeId(id)) : [...prev, id]
    );
  };

  const selectedItems = useMemo(
    () =>
      sortedItems.filter((item) =>
        selectedIds.some((selectedId) => normalizeId(selectedId) === normalizeId(getId(item)))
      ),
    [sortedItems, selectedIds, getId, normalizeId]
  );

  const unselectedItems = useMemo(
    () =>
      sortedItems.filter(
        (item) => !selectedIds.some((selectedId) => normalizeId(selectedId) === normalizeId(getId(item)))
      ),
    [sortedItems, selectedIds, getId, normalizeId]
  );

  const visibleSelectedItems = useMemo(
    () => selectedItems.filter((item) => matchesSearch(getSearchValue?.(item) ?? getLabel(item), search)),
    [selectedItems, search, getSearchValue, getLabel]
  );

  const visibleUnselectedItems = useMemo(
    () => unselectedItems.filter((item) => matchesSearch(getSearchValue?.(item) ?? getLabel(item), search)),
    [unselectedItems, search, getSearchValue, getLabel]
  );

  const unresolvedSelectedIds = useMemo(() => {
    if (loading) return [];
    const seen = new Set<string>();
    return selectedIds.filter((selectedId) => {
      const normalized = normalizeId(selectedId);
      if (seen.has(normalized)) return false;
      seen.add(normalized);
      return !sortedItems.some((item) => normalizeId(getId(item)) === normalized);
    });
  }, [loading, selectedIds, sortedItems, getId, normalizeId]);

  const visibleUnresolvedSelectedIds = useMemo(
    () => unresolvedSelectedIds.filter((id) => matchesSearch(id, search)),
    [unresolvedSelectedIds, search]
  );

  const selectVisible = () => {
    const prev = selectedIdsRef.current;
    const nextIds = visibleUnselectedItems.map(getId).filter((id) => !isIdSelected(id, prev));
    emitChange([...prev, ...nextIds]);
  };

  const clearAll = () => emitChange([]);

  const triggerLabels = [...selectedItems.map(getLabel), ...unresolvedSelectedIds];
  const triggerLabel = loading
    ? loadingLabel
    : selectedIds.length === 0
      ? placeholder
      : triggerLabels.length <= 2
        ? triggerLabels.join(', ')
        : selectedCountLabel(selectedIds.length);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) setSearch('');
  };

  return (
    <div>
      <Popover modal open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <button
            type="button"
            role="combobox"
            aria-expanded={open}
            disabled={disabled || loading}
            className={cn(
              'border-input ring-offset-background focus:ring-ring flex min-h-9 w-full items-center justify-between rounded-md border bg-white px-3 py-2 text-sm shadow-sm focus:ring-1 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
              selectedIds.length === 0 && 'text-[#878787]'
            )}
          >
            <span className="truncate text-left">{triggerLabel}</span>
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput placeholder={searchPlaceholder} value={search} onValueChange={setSearch} />
            {showSelectAll ? (
              <div className="flex items-center justify-end gap-3 border-b px-3 py-1.5">
                <button
                  type="button"
                  className="cursor-pointer text-xs font-medium text-[#282828] no-underline hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={visibleUnselectedItems.length === 0}
                  onClick={selectVisible}
                >
                  Select all
                </button>
                <button
                  type="button"
                  className="cursor-pointer text-xs font-medium text-[#282828] no-underline hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={selectedIds.length === 0}
                  onClick={clearAll}
                >
                  Clear all
                </button>
              </div>
            ) : null}
            <CommandList>
              <CommandEmpty>{emptyLabel}</CommandEmpty>
              {visibleSelectedItems.length > 0 || visibleUnresolvedSelectedIds.length > 0 ? (
                <CommandGroup heading={selectedGroupHeading}>
                  {visibleSelectedItems.map((item) => {
                    const id = getId(item);
                    return (
                      <CommandItem
                        key={`selected-${id}`}
                        value={getItemSearchValue(item)}
                        onSelect={() => toggleItem(id)}
                      >
                        <Check className="mr-2 h-4 w-4 shrink-0 opacity-100" />
                        {getLabel(item)}
                      </CommandItem>
                    );
                  })}
                  {visibleUnresolvedSelectedIds.map((id) => (
                    <CommandItem key={`unresolved-${id}`} value={id} onSelect={() => toggleItem(id)}>
                      <Check className="mr-2 h-4 w-4 shrink-0 opacity-100" />
                      <span className="truncate" title={id}>
                        {id}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
              {visibleUnselectedItems.length > 0 ? (
                <CommandGroup heading={allItemsGroupHeading}>
                  {visibleUnselectedItems.map((item) => {
                    const id = getId(item);
                    return (
                      <CommandItem key={id} value={getItemSearchValue(item)} onSelect={() => toggleItem(id)}>
                        <Check className="mr-2 h-4 w-4 shrink-0 opacity-0" />
                        {getLabel(item)}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              ) : null}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {selectedItems.length > 0 || unresolvedSelectedIds.length > 0 ? (
        <div className="mt-2 flex max-h-20 flex-wrap gap-2 overflow-y-auto rounded-md border border-[#EFF0F1] bg-[#FBFBFB] p-3">
          {selectedItems.map((item) => {
            const id = getId(item);
            const label = getLabel(item);
            return (
              <Badge
                key={id}
                variant="secondary"
                className="shrink-0 gap-1 border border-[#EFF0F1] bg-white pr-1 font-normal"
              >
                <span className="max-w-60 truncate">{label}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 hover:bg-black/10"
                  aria-label={`Remove ${label}`}
                  onClick={() => toggleItem(id)}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
          {unresolvedSelectedIds.map((id) => (
            <Badge
              key={`unresolved-${id}`}
              variant="secondary"
              className="shrink-0 gap-1 border border-[#EFF0F1] bg-white pr-1 font-normal"
            >
              <span className="max-w-60 truncate" title={id}>
                {id}
              </span>
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-black/10"
                aria-label={`Remove ${id}`}
                onClick={() => toggleItem(id)}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default MultiSelect;
