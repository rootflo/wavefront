import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@app/components/ui/tooltip';
import { cn } from '@app/lib/utils';
import { OPERATION_GROUPS } from './operations';
import { DatasourceOperationState } from './useDatasourceOperation';

/** The operation tiles, grouped by what they do. */
const OperationPicker = ({ op }: { op: DatasourceOperationState }) => {
  const { selectedOperation, chooseOperation } = op;
  return (
    <TooltipProvider delayDuration={300}>
      <div className="grid shrink-0 gap-4 lg:grid-cols-[2fr_3fr_2fr]">
        {OPERATION_GROUPS.map((group) => (
          <div key={group.title} className="flex min-w-0 flex-col gap-2">
            <div className="flex items-baseline gap-2">
              <h2 className="frost-text text-xs font-semibold tracking-wider uppercase">{group.title}</h2>
              <span className="frost-text-subtle truncate text-xs">{group.hint}</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-[repeat(auto-fit,minmax(150px,1fr))]">
              {group.operations.map((op) => {
                const active = op.id === selectedOperation;
                return (
                  <Tooltip key={op.id}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => chooseOperation(op.id)}
                        aria-pressed={active}
                        className={cn(
                          // One fixed height for every tile: a one-line name and at most two lines of summary.
                          'flex h-[4.75rem] cursor-pointer items-start gap-2.5 overflow-hidden rounded-xl border p-3 text-left transition-all',
                          active
                            ? op.destructive
                              ? 'border-rose-400/50 bg-rose-400/10 ring-1 ring-rose-400/30'
                              : 'border-brand/50 bg-brand/10 ring-brand/30 ring-1'
                            : 'frost-panel ring-frost-border hover:bg-frost-glass-strong ring-1'
                        )}
                      >
                        <span
                          className={cn(
                            'flex size-8 shrink-0 items-center justify-center rounded-lg',
                            op.destructive
                              ? 'bg-rose-400/15 text-rose-600 dark:text-rose-300'
                              : 'bg-brand/12 text-brand'
                          )}
                        >
                          <op.icon className="size-4" />
                        </span>
                        <span className="min-w-0">
                          <span className="frost-text block truncate text-sm font-medium">{op.label}</span>
                          <span className="frost-text-muted line-clamp-2 text-xs">{op.summary}</span>
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-64">
                      <p className="font-semibold">{op.label}</p>
                      <p className="mt-0.5">{op.summary}</p>
                      {op.postgresOnly ? (
                        <p className="mt-1 opacity-80">Postgres only. If any part fails, nothing is written.</p>
                      ) : null}
                      {op.destructive ? (
                        <p className="mt-1 opacity-80">Changes existing data; you’ll be asked to confirm.</p>
                      ) : null}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </TooltipProvider>
  );
};

export default OperationPicker;
