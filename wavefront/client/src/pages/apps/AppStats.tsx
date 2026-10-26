import { isLiveStatus } from '@app/lib/app-status';
import { cn } from '@app/lib/utils';
import { App } from '@app/types/app';
import { LayoutGrid } from 'lucide-react';
import React, { useEffect, useState } from 'react';

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

/** How many apps there are and how many of them are live, as a row of chips. */
const AppStats = ({ apps, className }: { apps: App[]; className?: string }) => {
  const liveCount = apps.filter((app) => isLiveStatus(app.status)).length;
  const offApps = apps.filter((app) => !isLiveStatus(app.status));
  const offLabel = offApps.every((app) => app.status?.toLowerCase() === 'stopped') ? 'stopped' : 'not live';

  return (
    <div className={cn('flex gap-2', className)}>
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
  );
};

export default AppStats;
