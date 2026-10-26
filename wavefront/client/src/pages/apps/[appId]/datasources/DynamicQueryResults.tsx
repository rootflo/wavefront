import { cn } from '@app/lib/utils';
import React from 'react';
import RowsWorkspace from './RowsWorkspace';

interface QueryOutcome {
  status?: 'success' | 'error';
  error?: string | null;
  description?: string;
  result?: unknown;
}

const isRowList = (value: unknown): value is Record<string, unknown>[] =>
  Array.isArray(value) && value.every((row) => typeof row === 'object' && row !== null && !Array.isArray(row));

const isOutcome = (value: unknown): value is QueryOutcome =>
  typeof value === 'object' && value !== null && ('result' in value || 'status' in value);

/** One query's rows in the same table as the Data tab (read-only), or its value as JSON when it isn't rows. */
const ResultBody = ({ value, name, title }: { value: unknown; name: string; title?: React.ReactNode }) =>
  isRowList(value) ? (
    <RowsWorkspace
      readOnly
      table={name}
      rows={value}
      status={
        value.length === 0 ? <p className="frost-text-muted py-6 text-center text-sm">No rows returned.</p> : undefined
      }
      title={title ?? <span className="frost-text font-mono text-sm font-semibold">{name}</span>}
      footerLabel={`${value.length} row${value.length === 1 ? '' : 's'}`}
      // Fills the height it is given; w-full + min-w-0 keep it within the dialog, so wide tables scroll inside.
      className="min-h-64 w-full min-w-0 flex-1"
    />
  ) : (
    <pre className="frost-glass border-frost-border frost-text max-h-80 max-w-full overflow-auto rounded-lg border p-3 font-mono text-xs whitespace-pre-wrap">
      {JSON.stringify(value, null, 2)}
    </pre>
  );

/**
 * A dynamic query's results. Execution answers one entry per query in the YAML, keyed by its id, each with a
 * status and its rows; every entry gets its own table. Anything else falls back to a single table or JSON.
 */
const DynamicQueryResults: React.FC<{ results: unknown }> = ({ results }) => {
  const entries =
    typeof results === 'object' && results !== null && !Array.isArray(results)
      ? Object.entries(results as Record<string, unknown>)
      : [];

  if (entries.length === 0 || !entries.every(([, value]) => isOutcome(value))) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ResultBody value={results} name="Results" />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-5">
      {(entries as [string, QueryOutcome][]).map(([queryId, outcome]) => {
        const failed = outcome.status === 'error';
        const heading = (
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="frost-text font-mono text-sm font-semibold">{queryId}</h4>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-xs font-medium',
                failed
                  ? 'bg-rose-400/15 text-rose-800 dark:text-rose-300'
                  : 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300'
              )}
            >
              {failed ? 'Failed' : 'Succeeded'}
            </span>
          </div>
        );
        return (
          // Tables share the height between them; an error or a JSON value takes only the room it needs.
          <section
            key={queryId}
            className={cn('flex min-h-0 min-w-0 flex-col gap-2', !failed && isRowList(outcome.result) && 'flex-1')}
          >
            {failed ? (
              <>
                {heading}
                <p className="text-sm text-red-500">{outcome.error || outcome.description || 'The query failed'}</p>
              </>
            ) : isRowList(outcome.result) ? (
              <ResultBody value={outcome.result} name={queryId} title={heading} />
            ) : (
              <>
                {heading}
                <ResultBody value={outcome.result} name={queryId} />
              </>
            )}
          </section>
        );
      })}
    </div>
  );
};

export default DynamicQueryResults;
