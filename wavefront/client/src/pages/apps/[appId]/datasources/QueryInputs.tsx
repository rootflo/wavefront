import FieldHelp from '@app/components/FieldHelp';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { cn } from '@app/lib/utils';
import { removeUnderscoreAndSentenceCase } from '@app/utils/string-formatting';
import { CircleAlert, Plus, X } from 'lucide-react';
import React, { useState } from 'react';
import FilterBuilder from './FilterBuilder';
import { QueryParameter } from './query-params';

interface QueryInputsProps {
  parameters: QueryParameter[];
  values: Record<string, string>;
  errors: Record<string, string>;
  onValueChange: (name: string, value: string) => void;
  /** Placeholders the YAML uses without declaring, per query. */
  undeclared: { queryId: string; names: string[] }[];
  /** Shown when a query has `{{filters}}`. */
  takesFilter: boolean;
  filter: string;
  onFilterChange: (filter: string) => void;
  limit: string;
  onLimitChange: (limit: string) => void;
  offset: string;
  onOffsetChange: (offset: string) => void;
  /** More than one query in the YAML, so it's worth saying which uses what. */
  multipleQueries: boolean;
}

const TYPE_STYLES: Record<QueryParameter['type'], string> = {
  string: 'bg-sky-400/15 text-sky-800 dark:text-sky-300',
  number: 'bg-violet-400/15 text-violet-800 dark:text-violet-300',
  boolean: 'bg-amber-400/15 text-amber-800 dark:text-amber-300',
  date: 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300',
};

/** The control that suits a parameter's type: a date picker, a number field, a true/false choice or text. */
const ParameterControl = ({
  parameter,
  value,
  invalid,
  onChange,
}: {
  parameter: QueryParameter;
  value: string;
  invalid: boolean;
  onChange: (value: string) => void;
}) => {
  const errorClass = invalid && 'border-red-500 focus-visible:border-red-500';
  if (parameter.type === 'boolean') {
    return (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={`param-${parameter.name}`} className={cn('h-9', errorClass)}>
          <SelectValue placeholder="Choose true or false" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">true</SelectItem>
          <SelectItem value="false">false</SelectItem>
        </SelectContent>
      </Select>
    );
  }
  return (
    <Input
      id={`param-${parameter.name}`}
      type={parameter.type === 'date' ? 'date' : parameter.type === 'number' ? 'number' : 'text'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={parameter.type === 'number' ? 'A number' : parameter.type === 'string' ? 'Text' : undefined}
      className={cn('h-9', errorClass)}
    />
  );
};

/**
 * The optional `{{filters}}` filter, folded away behind "Add filter" until it's wanted. Removing it clears it, so
 * a closed section never sends a filter nobody can see.
 */
const FilterSection = ({ filter, onFilterChange }: { filter: string; onFilterChange: (filter: string) => void }) => {
  const [open, setOpen] = useState(Boolean(filter));

  const help = (
    <FieldHelp ariaLabel="About the filter">
      The query has a <code>{'{{filters}}'}</code> placeholder. A filter here narrows its rows; without one, every row
      matches.
    </FieldHelp>
  );

  if (!open) {
    return (
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-brand inline-flex cursor-pointer items-center gap-1 text-sm font-medium"
        >
          <Plus className="size-4" />
          Add filter
        </button>
        {help}
      </div>
    );
  }

  return (
    <section className="border-frost-border flex flex-col gap-2.5 rounded-lg border p-3">
      <div className="flex items-center gap-1.5">
        <h3 className="frost-text text-sm font-semibold">Filter</h3>
        {help}
        <button
          type="button"
          onClick={() => {
            onFilterChange('');
            setOpen(false);
          }}
          className="frost-text-muted hover:text-frost-text ml-auto inline-flex cursor-pointer items-center gap-1 text-xs"
        >
          <X className="size-3.5" />
          Remove
        </button>
      </div>
      <FilterBuilder columns={[]} value={filter} onChange={onFilterChange} placeholder="e.g. status eq 'active'" />
    </section>
  );
};

/**
 * Everything a dynamic query takes when it runs: its declared parameters (each with a control for its type),
 * the `{{filters}}` filter when a query has one, and how many rows to fetch.
 */
const QueryInputs: React.FC<QueryInputsProps> = ({
  parameters,
  values,
  errors,
  onValueChange,
  undeclared,
  takesFilter,
  filter,
  onFilterChange,
  limit,
  onLimitChange,
  offset,
  onOffsetChange,
  multipleQueries,
}) => (
  <div className="flex flex-col gap-5">
    {parameters.length > 0 ? (
      <section className="flex flex-col gap-3">
        <h3 className="frost-text text-sm font-semibold">
          Parameters <span className="frost-text-muted ml-1 text-xs font-normal">all required</span>
        </h3>
        <div className="grid gap-4">
          {parameters.map((parameter) => (
            <div key={parameter.name} className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={`param-${parameter.name}`} className="flex min-w-0 items-center gap-2">
                <span className="frost-text truncate text-sm font-medium" title={parameter.name}>
                  {removeUnderscoreAndSentenceCase(parameter.name)}
                </span>
                <span className={cn('rounded-full px-1.5 py-px text-[10px] font-medium', TYPE_STYLES[parameter.type])}>
                  {parameter.type}
                </span>
                <code className="frost-text-subtle ml-auto shrink-0 font-mono text-[11px]">:{parameter.name}</code>
              </label>
              <ParameterControl
                parameter={parameter}
                value={values[parameter.name] ?? ''}
                invalid={Boolean(errors[parameter.name])}
                onChange={(value) => onValueChange(parameter.name, value)}
              />
              {errors[parameter.name] ? (
                <span className="text-xs text-red-500">{errors[parameter.name]}</span>
              ) : multipleQueries ? (
                <span className="frost-text-subtle truncate text-xs">Used by {parameter.usedBy.join(', ')}</span>
              ) : null}
            </div>
          ))}
        </div>
      </section>
    ) : null}

    {undeclared.length > 0 ? (
      <div className="flex items-start gap-2 rounded-lg bg-amber-400/10 px-3 py-2.5 text-xs text-amber-800 dark:text-amber-300">
        <CircleAlert className="mt-px size-4 shrink-0" />
        <div className="min-w-0">
          <p className="font-medium">Some placeholders aren&apos;t declared as parameters</p>
          {undeclared.map(({ queryId, names }) => (
            <p key={queryId} className="mt-0.5">
              {queryId} uses {names.map((name) => `:${name}`).join(', ')}. Add {names.length === 1 ? 'it' : 'them'}{' '}
              under <code>parameters</code> in the YAML, or the query will fail.
            </p>
          ))}
        </div>
      </div>
    ) : null}

    {takesFilter ? <FilterSection filter={filter} onFilterChange={onFilterChange} /> : null}

    <section className="flex flex-wrap items-end gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="frost-text-muted text-xs">Rows per query</span>
        <Input
          type="number"
          min={1}
          value={limit}
          onChange={(e) => onLimitChange(e.target.value)}
          className="h-9 w-28"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="frost-text-muted text-xs">Skip the first</span>
        <Input
          type="number"
          min={0}
          value={offset}
          onChange={(e) => onOffsetChange(e.target.value)}
          className="h-9 w-28"
        />
      </label>
      {parameters.length === 0 && !takesFilter ? (
        <p className="frost-text-muted pb-2 text-xs">This query takes no parameters.</p>
      ) : null}
    </section>
  </div>
);

export default QueryInputs;
