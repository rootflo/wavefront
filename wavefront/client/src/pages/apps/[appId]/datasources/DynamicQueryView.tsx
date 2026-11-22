import { Button } from '@app/components/ui/button';
import { Download, Loader2, Play, Rows3 } from 'lucide-react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { cn } from '@app/lib/utils';
import { DynamicQueryItem } from '@app/types/datasource';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeEditor from '@app/components/CodeEditor';
import { useEffect, useMemo, useState } from 'react';
import { buildDynamicQueryYaml } from './dynamic-query-utils';
import DynamicQueryResults from './DynamicQueryResults';
import QueryInputs from './QueryInputs';
import { collectParameters, undeclaredPlaceholders, usesFilters } from './query-params';
import { DynamicQueryRunOptions } from '@app/types/datasource';

const isEmptyResult = (result: unknown) =>
  result === null ||
  result === undefined ||
  (Array.isArray(result) && result.length === 0) ||
  (typeof result === 'object' && Object.keys(result as object).length === 0);

const DynamicQueryView = ({
  queryItems,
  queryCrud,
  selectedQuery,
  queryName,
  handleDynamicQueryEdit,
  handleClose,
  handleDynamicQueryExecute,
  handleDynamicQueryExport,
  exporting,
  executeResult,
  setExecuteResult,
  executing,
}: {
  queryItems: DynamicQueryItem[];
  setQueryCrud: React.Dispatch<
    React.SetStateAction<{
      view: boolean;
      edit: boolean;
      create: boolean;
      delete: boolean;
      execute: boolean;
    }>
  >;
  setQueryItems: React.Dispatch<React.SetStateAction<DynamicQueryItem[]>>;
  setSelectedQuery: React.Dispatch<React.SetStateAction<string | null>>;
  queryCrud: {
    view: boolean;
    edit: boolean;
    create: boolean;
    delete: boolean;
    execute: boolean;
  };
  selectedQuery: string | null;
  queryName: string;
  handleDynamicQueryEdit: (queryContent: string) => void;
  handleClose: () => void;
  handleDynamicQueryExecute: (params: Record<string, string>, options: DynamicQueryRunOptions) => void;
  /** Runs the query with the same parameters and downloads the result as a CSV. */
  handleDynamicQueryExport: (params: Record<string, string>, options: DynamicQueryRunOptions) => void;
  exporting: boolean;
  executeResult: Record<string, unknown>[];
  setExecuteResult: React.Dispatch<React.SetStateAction<Record<string, unknown>[]>>;
  executing: boolean;
}) => {
  const [queryContent, setQueryContent] = useState('');
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({});
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [runFilter, setRunFilter] = useState('');
  const [runLimit, setRunLimit] = useState('100');
  const [runOffset, setRunOffset] = useState('0');

  const parameters = useMemo(() => collectParameters(queryItems), [queryItems]);
  const undeclared = useMemo(() => undeclaredPlaceholders(queryItems), [queryItems]);
  const takesFilter = useMemo(() => usesFilters(queryItems), [queryItems]);

  // A different query starts from empty inputs.
  useEffect(() => {
    setParameterValues({});
    setFormErrors({});
    setRunFilter('');
    setRunLimit('100');
    setRunOffset('0');
  }, [queryItems]);

  const handleParameterChange = (parameterName: string, value: string) => {
    setParameterValues((prev) => ({
      ...prev,
      [parameterName]: value,
    }));

    if (formErrors[parameterName]) {
      setFormErrors((prev) => ({
        ...prev,
        [parameterName]: '',
      }));
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    parameters.forEach(({ name, type }) => {
      const value = parameterValues[name]?.trim();
      if (!value) errors[name] = 'Required';
      else if (type === 'number' && isNaN(Number(value))) errors[name] = 'Must be a number';
      else if (type === 'date' && isNaN(Date.parse(value))) errors[name] = 'Must be a date';
      else if (type === 'boolean' && !['true', 'false', '1', '0'].includes(value.toLowerCase()))
        errors[name] = 'Must be true or false';
    });
    if (!Number.isInteger(Number(runLimit)) || Number(runLimit) < 1)
      errors.__limit = 'Rows must be a whole number above 0';
    if (!Number.isInteger(Number(runOffset)) || Number(runOffset) < 0) errors.__offset = 'Skip must be 0 or more';

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const hasResults = !isEmptyResult(executeResult);

  const runOptions = (): DynamicQueryRunOptions => ({
    filter: takesFilter ? runFilter.trim() || undefined : undefined,
    limit: Number(runLimit),
    offset: Number(runOffset),
  });

  const handleExecuteQuery = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (validateForm()) {
      handleDynamicQueryExecute(parameterValues, runOptions());
      setExecuteResult([]);
    }
  };

  useEffect(() => {
    setQueryContent(buildDynamicQueryYaml(selectedQuery, queryName, queryItems));
  }, [selectedQuery, queryName, queryItems]);

  const isOpen =
    (queryCrud.view || queryCrud.edit || queryCrud.execute) && (queryItems.length > 0 || queryCrud.execute);

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      handleClose();
    }
  };

  const getDialogTitle = () => {
    if (queryCrud.execute) return 'Execute Query';
    if (queryCrud.edit) return 'Edit Dynamic Query';
    return queryName;
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent
        className={cn(
          'max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl',
          // Executing is a fixed-size workspace: inputs on the left, results on the right, each scrolling alone.
          queryCrud.execute &&
            'flex h-[calc(100dvh-2rem)] max-h-none flex-col gap-0 overflow-hidden p-0 sm:h-[88dvh] sm:w-[96vw] sm:max-w-[96vw] sm:p-0 lg:max-w-6xl'
        )}
      >
        <DialogHeader className={cn(queryCrud.execute && 'border-frost-border border-b px-5 py-4 pr-12')}>
          <DialogTitle>{getDialogTitle()}</DialogTitle>
          {queryCrud.execute && (queryName || selectedQuery) ? (
            <p className="frost-text-muted truncate font-mono text-xs">{queryName || selectedQuery}</p>
          ) : null}
        </DialogHeader>
        {(queryCrud.view || queryCrud.edit) && (
          <div className="border-frost-border w-full min-w-0 rounded-xl border">
            <CodeEditor
              className="frost-glass frost-text w-full min-w-0 rounded-xl p-4 font-mono text-sm font-normal outline-none"
              value={queryContent}
              height="400px"
              width="100%"
              maxWidth="100%"
              extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
              onChange={(value: string) => setQueryContent(value)}
              editable={queryCrud.edit}
              placeholder="Enter your dynamic query here..."
            />
          </div>
        )}
        {queryCrud.execute && (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
            {/* Inputs: what the query needs, with the run buttons always at the bottom of the pane. */}
            <form
              onSubmit={(e) => {
                handleExecuteQuery(e);
              }}
              className="border-frost-border flex min-h-0 shrink-0 flex-col border-b max-md:max-h-[50%] md:w-[340px] md:border-r md:border-b-0"
            >
              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                <QueryInputs
                  key={selectedQuery ?? undefined}
                  parameters={parameters}
                  values={parameterValues}
                  errors={formErrors}
                  onValueChange={handleParameterChange}
                  undeclared={undeclared}
                  takesFilter={takesFilter}
                  filter={runFilter}
                  onFilterChange={setRunFilter}
                  limit={runLimit}
                  onLimitChange={setRunLimit}
                  offset={runOffset}
                  onOffsetChange={setRunOffset}
                  multipleQueries={queryItems.length > 1}
                />
                {formErrors.__limit || formErrors.__offset ? (
                  <p className="mt-2 text-xs text-red-500">{formErrors.__limit || formErrors.__offset}</p>
                ) : null}
              </div>
              <div className="border-frost-border flex shrink-0 gap-2 border-t px-5 py-3">
                <Button type="submit" className="flex-1" loading={executing} disabled={exporting}>
                  <Play className="size-4" />
                  {hasResults && !executing ? 'Run again' : 'Execute'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  loading={exporting}
                  disabled={executing}
                  title="Run with these inputs and download the result as CSV"
                  onClick={() => {
                    if (validateForm()) handleDynamicQueryExport(parameterValues, runOptions());
                  }}
                >
                  <Download className="size-4" />
                  CSV
                </Button>
              </div>
            </form>

            {/* Results: the rest of the dialog, so tables get room to breathe. */}
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto p-5">
                {executing ? (
                  <div className="frost-text-muted m-auto flex flex-col items-center gap-3 text-sm">
                    <Loader2 className="text-brand size-6 animate-spin" />
                    Running the query…
                  </div>
                ) : hasResults ? (
                  <DynamicQueryResults results={executeResult} />
                ) : (
                  <div className="m-auto flex max-w-xs flex-col items-center gap-3 text-center">
                    <span className="bg-brand/12 text-brand flex size-12 items-center justify-center rounded-2xl">
                      <Rows3 className="size-5" />
                    </span>
                    <p className="frost-text text-sm font-medium">No results yet</p>
                    <p className="frost-text-muted text-xs">
                      {parameters.length > 0
                        ? 'Fill in the parameters on the left, then execute. The results appear here.'
                        : 'Execute the query to see its results here.'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {(queryCrud.edit || queryCrud.view) && (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            {queryCrud.edit && <Button onClick={() => handleDynamicQueryEdit(queryContent)}>Save</Button>}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
};
export default DynamicQueryView;
