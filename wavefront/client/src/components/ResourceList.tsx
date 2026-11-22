import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { Skeleton } from '@app/components/ui/skeleton';
import { cn } from '@app/lib/utils';
import { LayoutGrid, List } from 'lucide-react';
import { ListView } from '@app/lib/list-view';
import React from 'react';

const VIEW_OPTIONS = [
  { value: 'cards', label: 'Card view', icon: LayoutGrid },
  { value: 'table', label: 'Table view', icon: List },
] as const;

/** Two icon buttons with a knob that slides to the chosen one. For a header's desktop-only `extras`. */
export const ListViewToggle = ({ view, onChange }: { view: ListView; onChange: (view: ListView) => void }) => (
  <div
    role="radiogroup"
    aria-label="Layout"
    className="frost-control ring-frost-border relative inline-flex h-10 shrink-0 items-center rounded-[10px] border p-1 ring-1"
  >
    <span
      aria-hidden
      className="bg-brand absolute top-1 bottom-1 left-1 w-8 rounded-md shadow-[0_6px_14px_-6px_var(--color-brand)] transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] motion-reduce:transition-none"
      style={{ transform: view === 'table' ? 'translateX(100%)' : undefined }}
    />
    {VIEW_OPTIONS.map(({ value, label, icon: Icon }) => (
      <button
        key={value}
        type="button"
        role="radio"
        aria-checked={view === value}
        aria-label={label}
        title={label}
        onClick={() => onChange(value)}
        className={cn(
          'relative z-[1] flex h-full w-8 cursor-pointer items-center justify-center rounded-md transition-colors duration-200',
          'focus-visible:ring-brand/40 focus-visible:ring-2 focus-visible:outline-none',
          view === value ? 'text-white' : 'frost-text-muted hover:text-frost-text'
        )}
      >
        <Icon className="size-4" />
      </button>
    ))}
  </div>
);

interface ResourceListProps {
  view: ListView;
  /** One card per item; a phone always shows these, whatever the view. */
  cards: React.ReactNode;
  /** The whole table, shown in table view from md up. */
  table: React.ReactNode;
}

/** A Build page's items as a card grid or a table. */
const ResourceList = ({ view, cards, table }: ResourceListProps) =>
  view === 'cards' ? (
    <div className="-mx-1 -mt-2 min-h-0 flex-1 overflow-y-auto max-md:flex-none">
      <div className="grid gap-3 px-1 pt-2 pb-24 sm:grid-cols-2 sm:gap-6 sm:pb-10 lg:grid-cols-3">{cards}</div>
    </div>
  ) : (
    <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1 max-md:flex-none">
      <div data-mobile-cards className="flex flex-col gap-3 pb-24 md:hidden">
        {cards}
      </div>
      <div className="max-md:hidden">{table}</div>
    </div>
  );

// Column widths for the placeholder table: a name, an id, then a few short values and the actions.
const SKELETON_COLUMNS = ['w-32', 'w-48', 'w-20', 'w-16', 'w-24'];

/** Placeholders shaped like the list about to load: cards in card view, rows in table view (cards on a phone). */
export const ResourceListSkeleton = ({ view, count = 6 }: { view: ListView; count?: number }) => {
  const cards = Array.from({ length: count }).map((_, index) => <ResourceCardSkeleton key={index} showDescription />);
  return (
    <ResourceList
      view={view}
      cards={cards}
      table={
        <div aria-label="Loading" className="flex flex-col">
          {Array.from({ length: count + 1 }).map((_, row) => (
            <div key={row} className="border-frost-border flex items-center gap-8 border-b px-4 py-4 last:border-b-0">
              {SKELETON_COLUMNS.map((width, column) => (
                <Skeleton key={column} className={cn(row === 0 ? 'h-3 opacity-60' : 'h-4', width)} />
              ))}
              <Skeleton className={cn('ml-auto w-14', row === 0 ? 'h-3 opacity-60' : 'h-4')} />
            </div>
          ))}
        </div>
      }
    />
  );
};

export default ResourceList;
