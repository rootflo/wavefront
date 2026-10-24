import { Button } from '@app/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { cn, copyToClipboard } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { ArrowUpRight, Box, Check, Copy, MoreVertical, Pencil, Trash2 } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';

export interface ResourceCardMetadata {
  label: string;
  value: string;
  className?: string;
  isMono?: boolean;
  isCopyable?: boolean;
}

/** A coloured pill shown under the description, for values worth spotting in a list (a provider, a status). */
export interface ResourceCardChip {
  label: string;
  /** Colour classes, e.g. 'bg-emerald-400/15 text-emerald-800'. Defaults to a neutral pill. */
  className?: string;
}

export interface ResourceCardAction {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  onClick: (e: React.MouseEvent) => void;
  disabled?: boolean;
}

interface ResourceCardProps {
  title: string;
  description?: string;
  metadata: ResourceCardMetadata[];
  /** Optional coloured pills shown under the description. */
  chips?: ResourceCardChip[];
  /** Without it the card is not tappable and the menu has no Open item. */
  onClick?: () => void;
  /** Without it the menu has no Delete item. */
  onDeleteClick?: (e: React.MouseEvent) => void;
  /** Page-specific actions (Download, Pause, Verify ...) listed in the menu between Edit and Delete. */
  extraActions?: ResourceCardAction[];
  onEditClick?: (e: React.MouseEvent) => void;
  deleteTitle?: string;
  editTitle?: string;
  icon?: React.ComponentType<{ className?: string }>;
}

// Tints for the icon tile; the same title always gets the same one, so a list stays easy to scan.
const TILE_TINTS = [
  'bg-brand/12 text-brand',
  'bg-violet-500/15 text-violet-600 dark:text-violet-300',
  'bg-teal-500/15 text-teal-700 dark:text-teal-300',
  'bg-amber-500/15 text-amber-700 dark:text-amber-300',
];

const tintFor = (title: string) => {
  let hash = 0;
  for (const char of title) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TILE_TINTS[hash % TILE_TINTS.length];
};

// Values that mean nothing without their name in front ("Next run 12/03/2025").
const LABELLED_CHIPS = new Set(['created', 'updated', 'next run', 'last run']);
// Of those, the ones the wide layout moves into the footer.
const FOOTER_DATES = new Set(['created', 'updated', 'next run']);

const cardShell =
  'frost-card group relative flex cursor-pointer flex-col gap-4 overflow-hidden rounded-2xl border p-4 ring-1 ring-frost-border transition-all duration-300 hover:-translate-y-0.5 hover:bg-frost-glass-strong';

const ResourceCard: React.FC<ResourceCardProps> = ({
  title,
  description,
  metadata,
  chips: coloredChips,
  onClick,
  onDeleteClick,
  onEditClick,
  extraActions,
  deleteTitle = 'Delete',
  editTitle = 'Edit',
  icon: Icon = Box,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  // The id is a lookup value, not something to read: it lives in the menu and the footer, never in a chip.
  const copyable = metadata.find((item) => item.isCopyable);
  // A "Name" row that just repeats the title adds nothing.
  const chips = metadata.filter(
    (item) => !item.isCopyable && !(item.label.toLowerCase() === 'name' && item.value === title)
  );

  // Wide screens trade the chip row for a plain "tag · tag" line under the name and a footer with the date.
  const isDateChip = (item: ResourceCardMetadata) => FOOTER_DATES.has(item.label.toLowerCase());
  const dateChip = chips.find(isDateChip);
  const subline = chips
    .filter((item) => !isDateChip(item))
    .map((item) => (LABELLED_CHIPS.has(item.label.toLowerCase()) ? `${item.label} ${item.value}` : item.value))
    .join(' · ');

  const hasMenu = Boolean(onClick || onEditClick || onDeleteClick || copyable || extraActions?.length);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!copyable) return;
    const ok = await copyToClipboard(copyable.value);
    if (!ok) {
      notifyError('Failed to copy to clipboard');
      return;
    }
    notifySuccess('Copied to clipboard');
    setCopied(true);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div onClick={onClick} className={cn(cardShell, !onClick && 'cursor-default')}>
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0" />

      <div className="relative grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-start gap-3">
        <div className={cn('flex size-10 items-center justify-center rounded-xl', tintFor(title))}>
          <Icon className="size-5" />
        </div>
        <div className="min-w-0">
          <h3 className="frost-text truncate text-[15px] font-semibold tracking-normal normal-case">{title}</h3>
          {subline ? <p className="frost-text-muted mt-0.5 line-clamp-2 text-xs">{subline}</p> : null}
          {description ? (
            <p className="frost-text-muted mt-3 line-clamp-2 text-[13px] leading-snug font-normal tracking-normal normal-case">
              {description}
            </p>
          ) : null}
        </div>
        {hasMenu ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="More actions"
                className="frost-text-muted -mt-1 -mr-1 size-8 shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreVertical className="size-[18px]" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="frost-dialog border-frost-border min-w-52 rounded-xl p-1.5 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              {onEditClick || onClick ? (
                <DropdownMenuItem
                  className="frost-text cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px]"
                  onClick={onEditClick ?? (() => onClick?.())}
                >
                  {onEditClick ? (
                    <Pencil className="frost-text-muted size-4" />
                  ) : (
                    <ArrowUpRight className="frost-text-muted size-4" />
                  )}
                  {onEditClick ? editTitle : 'Open'}
                </DropdownMenuItem>
              ) : null}
              {extraActions?.map((action) => (
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
              {copyable ? (
                <DropdownMenuItem
                  className="frost-text cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px]"
                  onClick={(e) => void handleCopy(e)}
                >
                  <Copy className="frost-text-muted size-4" />
                  Copy ID
                  <span className="frost-text-subtle ml-auto max-w-24 truncate pl-3 font-mono text-[11px]">
                    {copyable.value}
                  </span>
                </DropdownMenuItem>
              ) : null}
              {onDeleteClick ? (
                <>
                  <DropdownMenuSeparator className="bg-frost-border" />
                  <DropdownMenuItem
                    className="cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px] text-red-600 focus:bg-red-500/10 focus:text-red-600 dark:text-red-400 dark:focus:text-red-400"
                    onClick={onDeleteClick}
                  >
                    <Trash2 className="size-4" />
                    {deleteTitle}
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <span />
        )}
      </div>

      {coloredChips && coloredChips.length > 0 ? (
        <div className="relative flex flex-wrap items-center gap-1.5">
          {coloredChips.map((chip) => (
            <span
              key={chip.label}
              className={cn(
                'rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-normal normal-case',
                chip.className || 'frost-control frost-text-muted ring-frost-border ring-1'
              )}
            >
              {chip.label}
            </span>
          ))}
        </div>
      ) : null}

      {copyable || dateChip ? (
        <div className="border-frost-border text-frost-text-muted relative flex items-center justify-between gap-2 border-t pt-3 text-xs">
          {copyable ? (
            <button
              type="button"
              title={copied ? 'Copied to clipboard' : 'Copy ID'}
              aria-label={copied ? 'Copied to clipboard' : 'Copy ID'}
              onClick={(e) => void handleCopy(e)}
              className="frost-control hover:text-frost-text text-frost-text-muted inline-flex max-w-[35%] cursor-pointer items-center gap-1 rounded-full px-1.5 py-px font-mono text-[10px] transition-colors"
            >
              <span className="truncate">{copyable.value}</span>
              {copied ? (
                <Check className="size-2.5 shrink-0 text-emerald-600" />
              ) : (
                <Copy className="size-2.5 shrink-0" />
              )}
            </button>
          ) : (
            <span />
          )}
          {dateChip ? (
            <span className="shrink-0">
              {dateChip.label} {dateChip.value}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

interface ResourceCardSkeletonProps {
  showDescription?: boolean;
  metadataCount?: number;
}

export const ResourceCardSkeleton: React.FC<ResourceCardSkeletonProps> = ({
  showDescription = false,
  metadataCount = 2,
}) => {
  return (
    <div className="frost-card animate-fade-in ring-frost-border flex flex-col gap-3 rounded-2xl border p-4 ring-1">
      <div className="flex items-start gap-3">
        <div className="bg-frost-text-subtle/20 size-10 shrink-0 animate-pulse rounded-xl" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="bg-frost-text-subtle/20 h-4 w-32 animate-pulse rounded-md" />
          {showDescription ? <div className="bg-frost-text-subtle/20 h-3.5 w-full animate-pulse rounded" /> : null}
        </div>
      </div>
      <div className="flex gap-1.5">
        {Array.from({ length: metadataCount }).map((_, index) => (
          <div key={index} className="bg-frost-text-subtle/20 h-5 w-16 animate-pulse rounded-full" />
        ))}
      </div>
    </div>
  );
};

export default ResourceCard;
