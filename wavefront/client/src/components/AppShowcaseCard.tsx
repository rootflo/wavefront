import { Button } from '@app/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@app/components/ui/dropdown-menu';
import { isLiveStatus, shortAgo } from '@app/lib/app-status';
import { cn, formatAppName } from '@app/lib/utils';
import { App } from '@app/types/app';
import dayjs from 'dayjs';
import {
  ArrowRight,
  ArrowUpRight,
  Box,
  Code2,
  GitBranch,
  Mic,
  MoreVertical,
  Pencil,
  Pin,
  PinOff,
  Trash2,
} from 'lucide-react';
import React from 'react';

interface AppShowcaseCardProps {
  app: App;
  /** Position in the deck: picks the colour and staggers the entrance. */
  index: number;
  /** One app on its own lays the card out wide on large screens. */
  wide?: boolean;
  pinned?: boolean;
  onTogglePin?: (app: App) => void;
  onOpen: (app: App, section?: string) => void;
  onEditClick: (app: App) => void;
  onDeleteClick: (app: App) => void;
}

// RGB triplets so one tint drives the banner, glow, avatar and button.
const TINTS = ['47 109 246', '139 92 246', '20 184 166'];

const SECTIONS = [
  { id: 'agents', label: 'Agents', icon: Box },
  { id: 'workflows', label: 'Flows', icon: GitBranch },
  { id: 'voice-agents', label: 'Voice', icon: Mic },
  { id: 'functions', label: 'Functions', icon: Code2 },
];

const menuItemClass = 'frost-text cursor-pointer gap-2.5 rounded-lg px-2.5 py-2.5 text-[13.5px]';

const AppShowcaseCard: React.FC<AppShowcaseCardProps> = ({
  app,
  index,
  wide,
  pinned,
  onTogglePin,
  onOpen,
  onEditClick,
  onDeleteClick,
}) => {
  const displayName = formatAppName(app.app_name);
  const initial = displayName.charAt(0);
  const live = isLiveStatus(app.status);
  const publicUrl = app.public_url?.replace(/^https?:\/\//, '');
  const updated = dayjs(app.updated_at || app.created_at);
  const tint = TINTS[index % TINTS.length];

  const facts = [
    {
      label: 'Deploy',
      value: app.deployment_type ? app.deployment_type[0].toUpperCase() + app.deployment_type.slice(1) : '—',
    },
    { label: 'Created', value: dayjs(app.created_at).format('MMM YYYY') },
    { label: 'Updated', value: shortAgo(updated) },
  ];

  return (
    <article
      onClick={() => onOpen(app)}
      data-tint={tint}
      style={{ ['--tint' as string]: tint, animationDelay: `${index * 90}ms` }}
      className={cn(
        'app-rise frost-card ring-frost-border group relative flex cursor-pointer flex-col overflow-hidden rounded-[22px] border shadow-[0_24px_50px_-30px_rgba(15,23,42,0.45)] ring-1',
        'transition-[transform,box-shadow,border-color] duration-300 ease-out hover:-translate-y-1.5 hover:border-[rgb(var(--tint)/0.55)] hover:shadow-[0_34px_60px_-30px_rgb(var(--tint)/0.6)]',
        wide && 'md:min-h-[340px] md:flex-row'
      )}
    >
      <div className={cn('relative h-28 shrink-0 sm:h-[150px]', wide && 'md:h-auto md:w-[42%]')}>
        <div className="absolute inset-0 overflow-hidden bg-[linear-gradient(135deg,rgb(var(--tint)/0.5),rgb(var(--tint)/0.08))]">
          <span className="pointer-events-none absolute -top-20 -right-12 size-56 rounded-full bg-[rgb(var(--tint)/0.5)] blur-[46px] transition-transform duration-700 group-hover:-translate-x-8 group-hover:translate-y-4 group-hover:scale-110" />
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 [background-image:radial-gradient(rgb(255_255_255/0.18)_1px,transparent_1px)] [mask-image:linear-gradient(120deg,black,transparent_70%)] [background-size:14px_14px] opacity-50"
          />
          <span
            aria-hidden
            className={cn(
              'pointer-events-none absolute right-3 -bottom-9 text-[120px] leading-none font-extrabold tracking-[-0.06em] text-transparent transition-transform duration-500 select-none [-webkit-text-stroke:1.5px_rgb(var(--tint)/0.55)] group-hover:-translate-x-2 group-hover:-rotate-3 sm:text-[150px]',
              wide && 'md:-bottom-14 md:text-[240px]'
            )}
          >
            {initial}
          </span>
        </div>

        <span className="absolute top-4 left-5 inline-flex items-center gap-2 rounded-full bg-black/40 px-3 py-1 text-xs font-semibold text-white backdrop-blur-md">
          <span className="relative size-2 rounded-full" style={{ background: live ? '#4ade80' : '#94a3b8' }}>
            {live ? <span className="app-ping absolute -inset-1 rounded-full border-2 border-[#4ade80]" /> : null}
          </span>
          <span className="capitalize">{live ? 'Live' : app.status || 'Unknown'}</span>
        </span>

        <div className="absolute top-3 right-3 flex items-center gap-1.5">
          {onTogglePin ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={pinned ? 'Unpin app' : 'Pin app'}
              title={pinned ? 'Unpin' : 'Pin to top'}
              aria-pressed={pinned}
              className={cn(
                'size-8 rounded-full text-white! backdrop-blur-md hover:text-white!',
                pinned ? 'bg-[rgb(var(--tint))] hover:bg-[rgb(var(--tint)/0.85)]' : 'bg-black/40 hover:bg-black/55'
              )}
              onClick={(e) => {
                e.stopPropagation();
                onTogglePin(app);
              }}
            >
              <Pin className={cn('size-4', pinned && 'fill-current')} />
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="More actions"
                className="size-8 rounded-full bg-black/40 text-white! backdrop-blur-md hover:bg-black/55 hover:text-white!"
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

        <div
          aria-hidden
          className={cn(
            'frost-glass-strong ring-frost-border absolute -bottom-6 left-5 z-10 flex size-[52px] items-center justify-center rounded-2xl text-[22px] font-extrabold text-[rgb(var(--tint))] shadow-[0_10px_24px_-10px_rgb(var(--tint)/0.7)] ring-1',
            wide && 'md:top-1/2 md:right-[-30px] md:bottom-auto md:left-auto md:size-[60px] md:-translate-y-1/2'
          )}
        >
          {initial}
        </div>
      </div>

      <div
        className={cn(
          'relative flex flex-1 flex-col gap-4 px-5 pt-9 pb-5',
          wide && 'md:justify-center md:py-7 md:pr-8 md:pl-11'
        )}
      >
        <div className="min-w-0">
          <h3
            className={cn(
              'frost-text truncate text-xl leading-tight font-bold tracking-tight',
              wide && 'md:text-[28px]'
            )}
          >
            {displayName}
          </h3>
          {publicUrl ? (
            <p
              className="frost-text-muted mt-1 flex items-center gap-1.5 font-mono text-[12.5px]"
              title={app.public_url}
            >
              <ArrowUpRight className="size-3.5 shrink-0" />
              <span className="truncate">{publicUrl}</span>
            </p>
          ) : null}
        </div>

        <div className="grid grid-cols-3 gap-2.5">
          {facts.map((fact) => (
            <div key={fact.label} className="frost-control ring-frost-border min-w-0 rounded-xl px-3 py-2 ring-1">
              <p className="frost-text-subtle text-[10.5px] font-semibold tracking-wider uppercase">{fact.label}</p>
              <p className="frost-text truncate text-[13px] font-semibold">{fact.value}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-4 gap-2">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onOpen(app, id);
              }}
              className="frost-control frost-text-muted ring-frost-border flex cursor-pointer flex-col items-center gap-1.5 rounded-[14px] px-1 pt-3 pb-2.5 text-[11.5px] font-semibold ring-1 transition-all duration-200 hover:-translate-y-0.5 hover:bg-[rgb(var(--tint)/0.16)] hover:text-[rgb(var(--tint))]"
            >
              <Icon className="size-[18px]" />
              <span className="max-w-full truncate">{label}</span>
            </button>
          ))}
        </div>

        <div className="mt-auto flex h-11 items-center justify-between rounded-xl bg-[linear-gradient(135deg,rgb(var(--tint)),rgb(var(--tint)/0.75))] px-4 text-sm font-semibold text-white shadow-[0_14px_26px_-16px_rgb(var(--tint))]">
          Open app
          <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" />
        </div>
      </div>
    </article>
  );
};

export default AppShowcaseCard;
