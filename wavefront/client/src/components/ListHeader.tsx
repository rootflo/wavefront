import { Button } from '@app/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { cn } from '@app/lib/utils';
import { MoreHorizontal, Plus, Search } from 'lucide-react';
import React, { useContext } from 'react';
import { createPortal } from 'react-dom';
import { PageActionsContext } from './PageActionsContext';
import FloatingCreateButton from './FloatingCreateButton';

export interface ListHeaderAction {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  onClick: () => void;
  disabled?: boolean;
}

interface ListHeaderProps {
  title?: string;
  /** How many items match the current search and filters. */
  count?: number;
  subtitle?: React.ReactNode;
  search?: { value: string; onChange: (value: string) => void; placeholder?: string };
  /** Filter controls; use {@link FilterSelect} so they look right as chips on a phone. */
  filters?: React.ReactNode;
  /** Desktop-only controls shown after the filters, such as a view switcher. */
  extras?: React.ReactNode;
  /** Download, Upload and the like: ghost buttons on desktop, the ⋯ menu on a phone. */
  secondary?: ListHeaderAction[];
  /** The page's main action: a solid button on desktop, the floating pill on a phone. */
  primary?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
    /** Defaults to a plus; use another for actions that are not "create", such as Save. */
    icon?: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  };
  className?: string;
}

/**
 * The heading block shared by every listing page: title with a count, a one-line subtitle, then
 * search, filters, secondary actions and the primary button, always in that order.
 */
const ListHeader = ({
  title,
  count,
  subtitle,
  search,
  filters,
  extras,
  secondary,
  primary,
  className,
}: ListHeaderProps) => {
  const slot = useContext(PageActionsContext);

  const toolbar = (
    <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-center md:gap-2.5">
      {search || secondary?.length ? (
        <div className="flex items-center gap-2">
          {search ? (
            <div className="relative min-w-0 flex-1 md:w-60 md:flex-none">
              <Search className="frost-text-subtle pointer-events-none absolute top-1/2 left-3.5 z-10 size-4 -translate-y-1/2" />
              <Input
                type="text"
                value={search.value}
                onChange={(e) => search.onChange(e.target.value)}
                placeholder={search.placeholder ?? 'Search'}
                aria-label={search.placeholder ?? 'Search'}
                className="h-[42px] rounded-xl pl-10 text-sm md:h-10 md:rounded-[10px] md:text-[13.5px]"
              />
            </div>
          ) : null}
          {secondary?.length ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="More actions"
                  className="size-[42px] shrink-0 rounded-xl md:hidden"
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="frost-dialog border-frost-border min-w-44 rounded-xl p-1.5">
                {secondary.map((action) => (
                  <DropdownMenuItem
                    key={action.label}
                    disabled={action.disabled}
                    className="frost-text cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px]"
                    onClick={action.onClick}
                  >
                    {action.icon ? <action.icon className="frost-text-muted size-4" /> : null}
                    {action.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      ) : null}

      {filters ? (
        <div className="no-scrollbar -mx-4 flex items-center gap-2 overflow-x-auto px-4 sm:-mx-8 sm:px-8 md:mx-0 md:overflow-visible md:px-0">
          {filters}
        </div>
      ) : null}

      <div className="hidden items-center gap-2.5 md:flex">
        {extras}
        {secondary?.map((action) => (
          <Button
            key={action.label}
            type="button"
            variant="ghost"
            disabled={action.disabled}
            className="frost-text-muted hover:text-frost-text h-10 rounded-[10px] px-3"
            onClick={action.onClick}
          >
            {action.icon ? <action.icon className="size-4" /> : null}
            {action.label}
          </Button>
        ))}
        {primary ? (
          <Button
            type="button"
            className="h-10 rounded-[10px] px-4 font-semibold"
            onClick={primary.onClick}
            disabled={primary.disabled}
          >
            {primary.icon ? (
              <primary.icon className="size-4" strokeWidth={2.4} />
            ) : (
              <Plus className="size-4" strokeWidth={2.4} />
            )}
            {primary.label}
          </Button>
        ) : null}
      </div>
    </div>
  );

  const floatingButton = primary ? (
    <FloatingCreateButton
      label={primary.label}
      onClick={primary.onClick}
      disabled={primary.disabled}
      icon={primary.icon}
    />
  ) : null;

  // A layout that owns the title offers a slot beside it; the controls go there so they share the title's row.
  if (!title && slot) {
    return slot.element
      ? createPortal(
          <>
            {toolbar}
            {floatingButton}
          </>,
          slot.element
        )
      : null;
  }

  return (
    <div
      className={cn(
        'mb-5 flex w-full shrink-0 flex-col gap-3 md:mb-8 md:flex-row md:items-end md:justify-between md:gap-5',
        className
      )}
    >
      {title ? (
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h1 className="frost-text text-2xl leading-tight font-bold tracking-tight md:text-[28px]">{title}</h1>
            {count !== undefined ? (
              <span className="frost-control frost-text-muted ring-frost-border rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ring-1">
                {count}
              </span>
            ) : null}
          </div>
          {subtitle ? (
            <p className="frost-text-muted mt-1 truncate text-[13.5px] md:mt-2 md:text-sm">{subtitle}</p>
          ) : null}
        </div>
      ) : null}
      {toolbar}
      {floatingButton}
    </div>
  );
};

interface FilterSelectProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  /** The value that means "no filter"; any other value tints the chip so a narrowed list is obvious. */
  allValue?: string;
  placeholder?: string;
}

/** A labelled dropdown that reads "Namespace: default" and sits in the header's filter row. */
export const FilterSelect = ({ label, value, onValueChange, options, allValue, placeholder }: FilterSelectProps) => {
  const active = allValue !== undefined && value !== allValue && value !== '';
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger
        aria-label={label}
        className={cn(
          'h-8 w-auto shrink-0 cursor-pointer gap-1.5 rounded-full px-3 text-[13px] font-medium md:h-10 md:min-w-44 md:rounded-[10px]',
          active && 'bg-brand/12 text-brand ring-brand/30 border-transparent'
        )}
      >
        <span className="flex items-center gap-1.5">
          <span className={cn('mr-1.5 font-normal', active ? 'text-brand/80' : 'frost-text-muted')}>{label}:</span>
          <SelectValue placeholder={placeholder ?? 'All'} />
        </span>
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} className="cursor-pointer" value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

export default ListHeader;
