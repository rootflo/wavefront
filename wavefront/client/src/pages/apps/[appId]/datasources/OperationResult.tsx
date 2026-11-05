import { Button } from '@app/components/ui/button';
import { cn } from '@app/lib/utils';
import { Check, CircleAlert, Copy } from 'lucide-react';
import RowsWorkspace from './RowsWorkspace';
import { DatasourceOperationState } from './useDatasourceOperation';

/** What the last run returned, and the API request the current inputs make. */
const OperationResult = ({ op }: { op: DatasourceOperationState }) => {
  const {
    datasourceId,
    running,
    previewing,
    result,
    copied,
    operation,
    chooseOperation,
    chooseTable,
    requestText,
    rereadRows,
    handleCopyRequest,
  } = op;
  return (
    <div className="flex min-w-0 flex-col gap-5">
      {result?.kind === 'rows' ? (
        // Rows get the same table as the Data tab: row key, columns, expand, details, edit, delete, history.
        <RowsWorkspace
          datasourceId={datasourceId}
          table={result.table}
          rows={result.records}
          status={
            result.records.length === 0 ? (
              <p className="frost-text-muted py-10 text-center text-sm">No rows.</p>
            ) : undefined
          }
          onChanged={() => void rereadRows()}
          onRefresh={() => void rereadRows()}
          refreshing={running || previewing}
          allowInsert={false}
          className="max-h-[36rem] min-h-48"
          title={
            <div className="min-w-0">
              <h2 className="frost-text text-sm font-semibold">
                Result <span className="frost-text-muted ml-1 font-normal">{result.title}</span>
              </h2>
              {result.note ? <p className="frost-text-muted truncate text-xs">{result.note}</p> : null}
            </div>
          }
          footerLabel={<span className="font-mono text-xs">{result.table}</span>}
        />
      ) : (
        <div className="frost-panel ring-frost-border flex min-h-48 min-w-0 flex-col rounded-xl border ring-1">
          <div className="border-frost-border flex items-center justify-between gap-3 border-b px-5 py-3.5">
            <h2 className="frost-text text-sm font-semibold">Result</h2>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2 p-5">
            {!result ? (
              <p className="frost-text-muted m-auto text-center text-sm">
                {operation.needsFilter === 'required'
                  ? 'Preview the matching rows, then run. The outcome shows here.'
                  : 'Run the operation to see the outcome here.'}
              </p>
            ) : result.kind === 'message' ? (
              <div
                className={cn(
                  'flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm',
                  result.ok
                    ? 'bg-emerald-400/10 text-emerald-800 dark:text-emerald-300'
                    : 'bg-rose-400/10 text-rose-800 dark:text-rose-300'
                )}
              >
                {result.ok ? (
                  <Check className="mt-0.5 size-4 shrink-0" />
                ) : (
                  <CircleAlert className="mt-0.5 size-4 shrink-0" />
                )}
                <span className="min-w-0 break-words">{result.text}</span>
              </div>
            ) : result.kind === 'tables' ? (
              result.names.length === 0 ? (
                <p className="frost-text-muted text-sm">No tables found.</p>
              ) : (
                <ul className="grid gap-1 sm:grid-cols-2">
                  {result.names.map((name) => (
                    <li key={name}>
                      <button
                        type="button"
                        onClick={() => {
                          chooseOperation('get-table-data');
                          chooseTable(name);
                        }}
                        title="Query this table"
                        className="frost-text hover:bg-frost-glass w-full cursor-pointer truncate rounded-md px-2 py-1 text-left font-mono text-xs"
                      >
                        {name}
                      </button>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </div>
        </div>
      )}

      <div className="frost-panel ring-frost-border min-w-0 rounded-xl border ring-1">
        <div className="border-frost-border flex items-center justify-between gap-3 border-b px-5 py-3">
          <h2 className="frost-text text-sm font-semibold">API request</h2>
          <Button variant="ghost" size="sm" onClick={() => void handleCopyRequest()}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>
        <pre className="frost-text max-h-56 overflow-auto p-5 font-mono text-xs whitespace-pre-wrap">{requestText}</pre>
      </div>
    </div>
  );
};

export default OperationResult;
