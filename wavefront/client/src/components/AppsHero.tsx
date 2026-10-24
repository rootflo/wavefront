import AppStats from '@app/components/AppStats';
import FloatingCreateButton from '@app/components/FloatingCreateButton';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { cn } from '@app/lib/utils';
import { App } from '@app/types/app';
import { CalendarDays, Plus, Search } from 'lucide-react';
import React, { useEffect, useRef } from 'react';

interface AppsHeroProps {
  /** First name of the signed-in user; the greeting falls back to "Welcome back" without it. */
  firstName?: string;
  apps: App[];
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

/** The apps home header: the date and a greeting on the left, finding and laying out apps on the right. */
const AppsHero: React.FC<AppsHeroProps> = ({ firstName, apps, onCreate, search, filters, extras }) => {
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

  return (
    <div className="relative mb-6 shrink-0 md:mb-8">
      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-stretch md:gap-8">
        <div className="flex min-w-0 flex-col">
          <p className="frost-text-muted flex items-center gap-2 text-xs font-semibold tracking-[0.1em] uppercase">
            <CalendarDays className="size-3.5" />
            {now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
          <h1 className="frost-text mt-2 text-[30px] leading-[1.08] font-extrabold tracking-[-0.03em] md:text-[44px]">
            {firstName ? (
              <>
                {greetingFor(now.getHours())},{' '}
                <span className="hero-shimmer bg-[linear-gradient(100deg,#2f6df6,#8b5cf6_45%,#14b8a6_90%)] bg-clip-text text-transparent dark:bg-[linear-gradient(100deg,#6b94ff,#a78bfa_45%,#2dd4bf_90%)]">
                  {firstName}
                </span>
              </>
            ) : (
              'Welcome back'
            )}
          </h1>
          <AppStats
            apps={apps}
            className="no-scrollbar -mx-4 mt-4 overflow-x-auto px-4 sm:-mx-8 sm:px-8 md:mx-0 md:flex-wrap md:px-0"
          />
          {filters ? (
            <div className="no-scrollbar -mx-4 mt-4 flex items-center gap-2 overflow-x-auto px-4 sm:-mx-8 sm:px-8 md:mx-0 md:mt-auto md:overflow-visible md:px-0 md:pt-4">
              {filters}
            </div>
          ) : null}
        </div>

        <div className="flex min-w-0 flex-col gap-3 md:w-[340px] md:justify-start">
          {search || extras ? (
            <div className="flex items-center gap-2">
              {search ? (
                <div className="relative min-w-0 flex-1">
                  <Search className="frost-text-subtle pointer-events-none absolute top-1/2 left-3.5 z-10 size-4 -translate-y-1/2" />
                  <Input
                    ref={searchRef}
                    type="text"
                    value={search.value}
                    onChange={(e) => search.onChange(e.target.value)}
                    placeholder="Search"
                    aria-label="Search"
                    className="h-11 rounded-xl pr-10 pl-10 text-sm md:h-10"
                  />
                  <kbd className="frost-text-muted border-frost-border bg-frost-glass pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded-md border px-1.5 font-mono text-[11px] md:block">
                    /
                  </kbd>
                </div>
              ) : null}
              {/* Same width as the search box beside it. */}
              {extras ? <div className="hidden min-w-0 flex-1 md:flex">{extras}</div> : null}
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
