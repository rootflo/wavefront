import FloatingCreateButton from '@app/components/FloatingCreateButton';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { isLiveStatus, shortAgo } from '@app/lib/app-status';
import { readLastApp } from '@app/lib/last-app';
import { cn, formatAppName } from '@app/lib/utils';
import { App } from '@app/types/app';
import dayjs from 'dayjs';
import { ArrowRight, CalendarDays, LayoutGrid, Plus, Search } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';

interface AppsHeroProps {
  /** First name of the signed-in user; the greeting falls back to "Welcome back" without it. */
  firstName?: string;
  apps: App[];
  onOpenApp: (app: App) => void;
  onCreate: () => void;
  search?: { value: string; onChange: (value: string) => void };
  filters?: React.ReactNode;
  extras?: React.ReactNode;
}

const greetingFor = (hour: number) => {
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 18) return 'Good afternoon';
  return 'Good evening';
};

/** Counts up from zero once, or just shows the number for people who ask for reduced motion. */
const CountUp = ({ to }: { to: number }) => {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setValue(to);
      return;
    }
    let frame = 0;
    let start: number | null = null;
    const step = (timestamp: number) => {
      if (start === null) start = timestamp;
      const progress = Math.min((timestamp - start) / 900, 1);
      setValue(Math.round(to * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [to]);

  return <span className="tabular-nums">{value}</span>;
};

const StatChip = ({ children, dot }: { children: React.ReactNode; dot?: 'live' | 'off' | 'grid' }) => (
  <span className="frost-glass ring-frost-border frost-text-muted inline-flex h-[34px] shrink-0 items-center gap-2 rounded-full pr-3.5 pl-2.5 text-[13px] ring-1">
    {dot === 'grid' ? <LayoutGrid className="text-brand size-4" /> : null}
    {dot === 'live' ? (
      <span className="relative size-2 rounded-full bg-emerald-500">
        <span className="app-ping absolute -inset-1 rounded-full border-2 border-emerald-500" />
      </span>
    ) : null}
    {dot === 'off' ? <span className="bg-frost-text-subtle size-2 rounded-full" /> : null}
    {children}
  </span>
);

/** The apps home header: a greeting, the state of your apps at a glance, a way back to the latest app, and the controls. */
const AppsHero: React.FC<AppsHeroProps> = ({ firstName, apps, onOpenApp, onCreate, search, filters, extras }) => {
  const searchRef = useRef<HTMLInputElement>(null);
  const now = new Date();

  // Pressing "/" anywhere on the page jumps to the search box, unless you are already typing somewhere.
  useEffect(() => {
    if (!search) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return;
      event.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [search]);

  const liveCount = apps.filter((app) => isLiveStatus(app.status)).length;
  const offApps = apps.filter((app) => !isLiveStatus(app.status));
  const offLabel = offApps.every((app) => app.status?.toLowerCase() === 'stopped') ? 'stopped' : 'not live';

  // The app the user was last inside, remembered in this browser; failing that, the one that changed most
  // recently. With a single app there is nothing to jump between.
  const [lastOpened] = useState(readLastApp);
  const lastUsed = lastOpened ? apps.find((app) => app.id === lastOpened.id) : undefined;
  const latest =
    apps.length > 1
      ? (lastUsed ??
        [...apps].sort(
          (a, b) => dayjs(b.updated_at || b.created_at).valueOf() - dayjs(a.updated_at || a.created_at).valueOf()
        )[0])
      : undefined;
  const openedAgo = lastUsed && lastOpened ? shortAgo(dayjs(lastOpened.at)) : null;

  return (
    <div className="relative mb-6 shrink-0 md:mb-8">
      <div className="grid items-end gap-5 md:grid-cols-[minmax(0,1fr)_auto] md:gap-8">
        <div className="min-w-0">
          <p className="frost-text-muted flex items-center gap-2 text-xs font-semibold tracking-[0.1em] uppercase">
            <CalendarDays className="size-3.5" />
            {now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
          <h1 className="frost-text mt-2 text-[30px] leading-[1.08] font-extrabold tracking-[-0.03em] md:text-[44px]">
            {firstName ? (
              <>
                {greetingFor(now.getHours())},<br />
                <span className="hero-shimmer bg-[linear-gradient(100deg,#2f6df6,#8b5cf6_45%,#14b8a6_90%)] bg-clip-text text-transparent dark:bg-[linear-gradient(100deg,#6b94ff,#a78bfa_45%,#2dd4bf_90%)]">
                  {firstName}
                </span>
              </>
            ) : (
              'Welcome back'
            )}
          </h1>
          <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4 sm:-mx-8 sm:px-8 md:mx-0 md:flex-wrap md:px-0">
            <StatChip dot="grid">
              <b className="frost-text text-[15px] font-bold">
                <CountUp to={apps.length} />
              </b>
              {apps.length === 1 ? 'app' : 'apps'}
            </StatChip>
            <StatChip dot="live">
              <b className="frost-text text-[15px] font-bold">
                <CountUp to={liveCount} />
              </b>
              live
            </StatChip>
            {offApps.length > 0 ? (
              <StatChip dot="off">
                <b className="frost-text text-[15px] font-bold">
                  <CountUp to={offApps.length} />
                </b>
                {offLabel}
              </StatChip>
            ) : null}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-3 md:w-[340px]">
          {latest ? (
            <button
              type="button"
              onClick={() => onOpenApp(latest)}
              className="frost-card ring-frost-border group grid cursor-pointer grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border p-3 text-left ring-1 transition-all duration-200 hover:-translate-y-0.5 hover:border-violet-400/50 hover:shadow-[0_20px_40px_-26px_rgba(139,92,246,0.7)]"
            >
              <span className="flex size-11 items-center justify-center rounded-[13px] bg-[linear-gradient(135deg,#8b5cf6,#5b3bb5)] text-lg font-extrabold text-white uppercase">
                {formatAppName(latest.app_name).charAt(0)}
              </span>
              <span className="min-w-0">
                <span className="frost-text-subtle block text-[11px] font-semibold tracking-[0.08em] uppercase">
                  Jump back in
                </span>
                <span className="frost-text block truncate text-[15.5px] leading-tight font-bold">
                  {formatAppName(latest.app_name)}
                </span>
                <span className="frost-text-muted block text-xs">
                  {latest === lastUsed && openedAgo
                    ? `Opened ${openedAgo === 'Just now' ? 'just now' : openedAgo}`
                    : `Updated ${shortAgo(dayjs(latest.updated_at || latest.created_at))}`}
                </span>
              </span>
              <span className="bg-brand flex size-8 items-center justify-center rounded-full text-white transition-transform duration-200 group-hover:translate-x-0.5">
                <ArrowRight className="size-4" />
              </span>
            </button>
          ) : null}

          {search || filters || extras ? (
            <div className="flex flex-col gap-3">
              {search ? (
                <div className="relative">
                  <Search className="frost-text-subtle pointer-events-none absolute top-1/2 left-3.5 z-10 size-4 -translate-y-1/2" />
                  <Input
                    ref={searchRef}
                    type="text"
                    value={search.value}
                    onChange={(e) => search.onChange(e.target.value)}
                    placeholder="Search apps"
                    aria-label="Search apps"
                    className="h-11 rounded-xl pr-10 pl-10 text-sm"
                  />
                  <kbd className="frost-text-muted border-frost-border bg-frost-glass pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded-md border px-1.5 font-mono text-[11px] md:block">
                    /
                  </kbd>
                </div>
              ) : null}
              {filters || extras ? (
                <div className="no-scrollbar -mx-4 flex items-center gap-2 overflow-x-auto px-4 sm:-mx-8 sm:px-8 md:mx-0 md:grid md:grid-cols-2 md:overflow-visible md:px-0 md:[&_button]:w-full md:[&_button]:min-w-0">
                  {filters}
                  <span className="hidden md:contents">{extras}</span>
                </div>
              ) : null}
            </div>
          ) : null}

          <Button
            type="button"
            onClick={onCreate}
            className={cn(
              'hidden h-11 rounded-xl border-0 bg-[linear-gradient(135deg,#2f6df6,#8b5cf6)] px-5 text-sm font-semibold text-white shadow-[0_16px_30px_-16px_#8b5cf6] md:inline-flex',
              'hover:bg-[linear-gradient(135deg,#2f6df6,#8b5cf6)] hover:brightness-110'
            )}
          >
            <Plus className="size-4" strokeWidth={2.4} />
            Create app
          </Button>
        </div>
      </div>

      <FloatingCreateButton label="Create app" onClick={onCreate} />
    </div>
  );
};

export default AppsHero;
