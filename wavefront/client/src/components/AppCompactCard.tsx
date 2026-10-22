import { Button } from '@app/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { isLiveStatus } from '@app/lib/app-status';
import { cn, formatAppName } from '@app/lib/utils';
import { App } from '@app/types/app';
import { ArrowUpRight, Box, Code2, GitBranch, Mic, MoreVertical, Pencil, Pin, PinOff, Trash2 } from 'lucide-react';
import React from 'react';

interface AppCompactCardProps {
  app: App;
  index: number;
  pinned?: boolean;
  onTogglePin?: (app: App) => void;
  onOpen: (app: App, section?: string) => void;
  onEditClick: (app: App) => void;
  onDeleteClick: (app: App) => void;
}

// Same colours as the large cards, as RGB triplets so one tint drives the avatar, glow and pin.
const TINTS = ['47 109 246', '139 92 246', '20 184 166'];

const menuItemClass = 'frost-text cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px]';

const SECTIONS = [
  { id: 'agents', label: 'Agents', icon: Box },
  { id: 'workflows', label: 'Flows', icon: GitBranch },
  { id: 'voice-agents', label: 'Voice', icon: Mic },
  { id: 'functions', label: 'Functions', icon: Code2 },
];

/** The small tile used when many cards share a row: avatar, name, domain and a status light. */
const AppCompactCard: React.FC<AppCompactCardProps> = ({
  app,
  index,
  pinned,
  onTogglePin,
  onOpen,
  onEditClick,
  onDeleteClick,
}) => {
  const displayName = formatAppName(app.app_name);
  const live = isLiveStatus(app.status);
  const publicUrl = app.public_url?.replace(/^https?:\/\//, '');
  const tint = TINTS[index % TINTS.length];

  return (
    <article
      onClick={() => onOpen(app)}
      data-tint={tint}
      style={{ ['--tint' as string]: tint, animationDelay: `${Math.min(index, 12) * 30}ms` }}
      className="app-rise frost-card ring-frost-border group relative flex cursor-pointer flex-col gap-3 overflow-hidden rounded-2xl border p-3 ring-1 transition-[transform,box-shadow,border-color] duration-200 ease-out hover:-translate-y-1 hover:border-[rgb(var(--tint)/0.55)] hover:shadow-[0_22px_40px_-24px_rgb(var(--tint)/0.65)]"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-14 bg-[linear-gradient(135deg,rgb(var(--tint)/0.28),rgb(var(--tint)/0))]"
      />

      <div className="relative flex items-start justify-between gap-1">
        <div className="frost-glass-strong ring-frost-border flex size-9 items-center justify-center rounded-xl text-base font-extrabold text-[rgb(var(--tint))] uppercase shadow-[0_8px_18px_-10px_rgb(var(--tint)/0.7)] ring-1">
          {displayName.charAt(0)}
        </div>
        <div className="-mt-1 -mr-1 flex items-center">
          {pinned ? <Pin className="size-3.5 fill-current text-[rgb(var(--tint))]" aria-label="Pinned" /> : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="More actions"
                className="frost-text-muted size-8 shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreVertical className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="frost-dialog border-frost-border min-w-52 rounded-xl p-1.5 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <DropdownMenuItem className={menuItemClass} onClick={() => onOpen(app)}>
                <ArrowUpRight className="frost-text-muted size-4" />
                Open
              </DropdownMenuItem>
              <DropdownMenuItem className={menuItemClass} onClick={() => onEditClick(app)}>
                <Pencil className="frost-text-muted size-4" />
                Edit
              </DropdownMenuItem>
              {onTogglePin ? (
                <DropdownMenuItem className={menuItemClass} onClick={() => onTogglePin(app)}>
                  {pinned ? (
                    <PinOff className="frost-text-muted size-4" />
                  ) : (
                    <Pin className="frost-text-muted size-4" />
                  )}
                  {pinned ? 'Unpin' : 'Pin to top'}
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuSeparator className="bg-frost-border" />
              <DropdownMenuItem
                className="cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px] text-red-600 focus:bg-red-500/10 focus:text-red-600 dark:text-red-400 dark:focus:text-red-400"
                onClick={() => onDeleteClick(app)}
              >
                <Trash2 className="size-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="relative min-w-0">
        <h3
          className="frost-text truncate text-[13.5px] leading-tight font-semibold tracking-normal normal-case"
          title={displayName}
        >
          {displayName}
        </h3>
        {publicUrl ? (
          <p
            className="frost-text-muted mt-0.5 truncate font-mono text-[11px] tracking-normal normal-case"
            title={app.public_url}
          >
            {publicUrl}
          </p>
        ) : null}
      </div>

      <div className="frost-text-muted relative flex items-center gap-1.5 text-[11px] font-medium capitalize">
        <span className={cn('size-1.5 shrink-0 rounded-full', live ? 'bg-emerald-500' : 'bg-frost-text-subtle')} />
        <span className="truncate">{live ? 'Live' : app.status || 'Unknown'}</span>
      </div>
      <div className="relative grid grid-cols-4 gap-1">
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            title={label}
            aria-label={`${label} in ${displayName}`}
            onClick={(e) => {
              e.stopPropagation();
              onOpen(app, id);
            }}
            className="frost-control frost-text-muted ring-frost-border flex h-8 cursor-pointer items-center justify-center rounded-lg ring-1 transition-colors hover:bg-[rgb(var(--tint)/0.16)] hover:text-[rgb(var(--tint))]"
          >
            <Icon className="size-3.5" />
          </button>
        ))}
      </div>
    </article>
  );
};

export default AppCompactCard;
