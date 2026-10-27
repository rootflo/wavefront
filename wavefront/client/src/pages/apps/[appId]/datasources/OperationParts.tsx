import FieldHelp from '@app/components/FieldHelp';
import { Textarea } from '@app/components/ui/textarea';
import { cn } from '@app/lib/utils';
import React from 'react';

// Small presentational pieces of the datasource operations panel

export const Step = ({
  number,
  title,
  hint,
  action,
  children,
}: {
  number: number;
  title: string;
  hint?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) => (
  <section className="flex gap-3">
    <span className="bg-brand/12 text-brand flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
      {number}
    </span>
    <div className="flex min-w-0 flex-1 flex-col gap-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="frost-text text-sm font-semibold">{title}</h3>
          {hint ? <p className="frost-text-muted text-xs">{hint}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </div>
  </section>
);

/**
 * A labelled input with its help behind an info icon. The icon sits outside the
 * <label> (a button inside one would take its clicks), so the label points at
 * the input by id instead.
 */
export const Field = ({
  label,
  help,
  className,
  children,
}: {
  label: string;
  help?: React.ReactNode;
  className?: string;
  children: React.ReactElement<{ id?: string }>;
}) => {
  const id = React.useId();
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-center gap-1.5">
        <label htmlFor={id} className="frost-text-muted text-xs">
          {label}
        </label>
        {help ? (
          <FieldHelp ariaLabel={`About ${label}`} contentClassName="max-w-sm">
            <div className="flex flex-col gap-1.5 leading-snug">{help}</div>
          </FieldHelp>
        ) : null}
      </div>
      {React.cloneElement(children, { id })}
    </div>
  );
};

/** Switches a step between the guided form and raw JSON. */
export const ModeSwitch = ({ json, onChange }: { json: boolean; onChange: (json: boolean) => void }) => (
  <div className="frost-control ring-frost-border inline-flex rounded-md p-0.5 text-xs ring-1">
    {[
      { value: false, label: 'Form' },
      { value: true, label: 'JSON' },
    ].map((option) => (
      <button
        key={option.label}
        type="button"
        onClick={() => onChange(option.value)}
        className={cn(
          'cursor-pointer rounded px-2 py-0.5 transition-colors',
          json === option.value ? 'bg-brand text-white' : 'frost-text-muted hover:text-frost-text'
        )}
      >
        {option.label}
      </button>
    ))}
  </div>
);

export const JsonBox = ({
  value,
  onChange,
  rows = 10,
}: {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
}) => (
  <Textarea
    value={value}
    onChange={(e) => onChange(e.target.value)}
    spellCheck={false}
    rows={rows}
    className="resize-y font-mono text-xs leading-relaxed"
  />
);
