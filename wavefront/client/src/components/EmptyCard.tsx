import { Button } from '@app/components/ui/button';
import { Plus, Search, Sparkles } from 'lucide-react';
import React from 'react';

interface EmptyProps {
  title: string;
  description: string;
  /** Leave empty when there is nothing the person can do about it, and no button is shown. */
  actionText: string;
  onActionClick: () => void;
  icon?: React.ComponentType<{ className?: string }>;
}

/** "No results" states read as a miss, not an invitation, so they get a search icon and a quieter button. */
const isNoMatch = (title: string, description: string) => /match|search|no results/i.test(`${title} ${description}`);

export function EmptyStateCard({ title, description, actionText, onActionClick, icon }: EmptyProps) {
  const noMatch = isNoMatch(title, description);
  const Icon = icon ?? (noMatch ? Search : Sparkles);

  return (
    <div className="frost-card ring-frost-border relative isolate flex w-full max-w-xl flex-col items-center gap-3 overflow-hidden rounded-2xl border border-dashed p-8 text-center ring-1 sm:p-10">
      <div aria-hidden className="frost-card-glow pointer-events-none absolute inset-0 -z-10" />
      <div
        aria-hidden
        className="bg-brand/20 pointer-events-none absolute -top-16 left-1/2 -z-10 size-48 -translate-x-1/2 rounded-full blur-3xl"
      />
      <div className="bg-brand/12 text-brand ring-brand/20 flex size-14 items-center justify-center rounded-2xl ring-1">
        <Icon className="size-6" />
      </div>
      <h3 className="frost-text text-lg font-semibold tracking-normal normal-case">{title}</h3>
      <p className="frost-text-muted max-w-sm text-sm font-normal tracking-normal normal-case">{description}</p>
      {actionText ? (
        <Button
          variant={noMatch ? 'outline' : 'default'}
          className="mt-1 h-10 rounded-[10px] px-4 font-semibold normal-case"
          onClick={onActionClick}
        >
          {noMatch ? null : <Plus className="size-4" strokeWidth={2.4} />}
          {actionText}
        </Button>
      ) : null}
    </div>
  );
}
