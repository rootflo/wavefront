import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { cn } from '@app/lib/utils';
import { CircleAlert, Eye, Play } from 'lucide-react';
import FilterBuilder from './FilterBuilder';
import ValuesEditor from './ValuesEditor';
import { INSERT_MULTI_TEMPLATE, UPDATE_MULTI_TEMPLATE } from './operations';
import { Step, ModeSwitch, JsonBox } from './OperationParts';
import { DatasourceOperationState } from './useDatasourceOperation';

/** The chosen operation's inputs, as numbered steps, with the run button. */
const OperationForm = ({ op }: { op: DatasourceOperationState }) => {
  const {
    selectedOperation,
    running,
    previewing,
    table,
    filter,
    setFilter,
    limit,
    setLimit,
    offset,
    setOffset,
    select,
    setSelect,
    orderBy,
    setOrderBy,
    groupBy,
    setGroupBy,
    expand,
    setExpand,
    join,
    setJoin,
    showMoreOptions,
    setShowMoreOptions,
    valuesAsJson,
    setValuesAsJson,
    pairs,
    setPairs,
    insertJson,
    setInsertJson,
    updateJson,
    setUpdateJson,
    insertMultiJson,
    setInsertMultiJson,
    updateMultiJson,
    setUpdateMultiJson,
    requireAllMatched,
    setRequireAllMatched,
    operation,
    tablesQuery,
    tables,
    columns,
    chooseTable,
    problems,
    handleRun,
    handlePreview,
  } = op;
  let step = 0;
  const nextStep = () => (step += 1);

  return (
    <div className="frost-panel ring-frost-border flex min-w-0 flex-col rounded-xl border ring-1">
      <div className="border-frost-border flex items-center gap-3 border-b px-5 py-3.5">
        <operation.icon className={cn('size-4', operation.destructive ? 'text-rose-500' : 'text-brand')} />
        <h2 className="frost-text text-sm font-semibold">{operation.label}</h2>
        {operation.postgresOnly ? (
          <span className="frost-text-muted rounded-full bg-amber-400/15 px-2 py-0.5 text-[11px] text-amber-800 dark:text-amber-300">
            Postgres only · all or nothing
          </span>
        ) : null}
      </div>

      <div className="flex flex-col gap-6 p-5">
        {selectedOperation === 'get-table-names' && (
          <p className="frost-text-muted text-sm">
            Nothing to set up. Run it to list every table this datasource can read.
          </p>
        )}

        {operation.needsTable && (
          <Step number={nextStep()} title="Table" hint={tablesQuery.isLoading ? 'Loading tables…' : undefined}>
            <Select value={table} onValueChange={chooseTable}>
              <SelectTrigger className="h-10 font-mono">
                <SelectValue placeholder="Pick a table" />
              </SelectTrigger>
              <SelectContent>
                {tables.map((name) => (
                  <SelectItem key={name} value={name} className="font-mono">
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Step>
        )}

        {operation.needsFilter && (
          <Step
            number={nextStep()}
            title={operation.needsFilter === 'required' ? 'Which rows' : 'Filter (optional)'}
            hint={
              operation.needsFilter === 'required'
                ? `Every row that matches is ${selectedOperation === 'delete-rows' ? 'deleted' : 'updated'}. A filter is required.`
                : 'Leave empty for all rows.'
            }
            action={
              operation.needsFilter === 'required' ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handlePreview()}
                  loading={previewing}
                  disabled={!table || !filter.trim() || previewing}
                >
                  <Eye className="size-4" />
                  Preview matching rows
                </Button>
              ) : null
            }
          >
            <FilterBuilder
              columns={columns}
              value={filter}
              onChange={setFilter}
              placeholder="e.g. status eq 'active'"
            />
          </Step>
        )}

        {selectedOperation === 'get-table-data' && (
          <Step number={nextStep()} title="Options">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="frost-text-muted text-xs">Rows to fetch</span>
                <Input type="number" min={1} value={limit} onChange={(e) => setLimit(e.target.value)} className="h-9" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="frost-text-muted text-xs">Skip the first</span>
                <Input
                  type="number"
                  min={0}
                  value={offset}
                  onChange={(e) => setOffset(e.target.value)}
                  className="h-9"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="frost-text-muted text-xs">Columns</span>
                <Input
                  value={select}
                  onChange={(e) => setSelect(e.target.value)}
                  placeholder={columns.length ? columns.slice(0, 3).join(', ') : 'All columns'}
                  className="h-9 font-mono text-xs"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="frost-text-muted text-xs">Sort by</span>
                <Input
                  value={orderBy}
                  onChange={(e) => setOrderBy(e.target.value)}
                  placeholder={`${columns[0] ?? 'created_at'} desc`}
                  className="h-9 font-mono text-xs"
                />
              </label>
              {showMoreOptions ? (
                <>
                  <label className="flex flex-col gap-1.5">
                    <span className="frost-text-muted text-xs">Group by</span>
                    <Input
                      value={groupBy}
                      onChange={(e) => setGroupBy(e.target.value)}
                      className="h-9 font-mono text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1.5">
                    <span className="frost-text-muted text-xs">Expand</span>
                    <Input
                      value={expand}
                      onChange={(e) => setExpand(e.target.value)}
                      className="h-9 font-mono text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 sm:col-span-2">
                    <span className="frost-text-muted text-xs">Join</span>
                    <Input value={join} onChange={(e) => setJoin(e.target.value)} className="h-9 font-mono text-xs" />
                  </label>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowMoreOptions(true)}
                  className="text-brand w-fit cursor-pointer text-xs font-medium sm:col-span-2"
                >
                  More options: group by, expand, join
                </button>
              )}
            </div>
          </Step>
        )}

        {(selectedOperation === 'insert-rows' || selectedOperation === 'update-rows') && (
          <Step
            number={nextStep()}
            title={selectedOperation === 'insert-rows' ? 'Values' : 'New values'}
            hint={
              valuesAsJson
                ? selectedOperation === 'insert-rows'
                  ? 'A row object, or a list of them to insert several at once.'
                  : 'An object of column names to their new values.'
                : selectedOperation === 'insert-rows'
                  ? 'One row. Switch to JSON to insert several.'
                  : 'Only these columns change; the rest keep their values.'
            }
            action={<ModeSwitch json={valuesAsJson} onChange={setValuesAsJson} />}
          >
            {valuesAsJson ? (
              selectedOperation === 'insert-rows' ? (
                <JsonBox value={insertJson} onChange={setInsertJson} />
              ) : (
                <JsonBox value={updateJson} onChange={setUpdateJson} rows={6} />
              )
            ) : (
              <ValuesEditor pairs={pairs} onChange={setPairs} columns={columns} />
            )}
          </Step>
        )}

        {selectedOperation === 'insert-multi' && (
          <Step
            number={nextStep()}
            title="Tables and rows"
            hint='One entry per table: "table_name" and "data" (a list of rows). If any table fails, none are written.'
            action={
              <button
                type="button"
                onClick={() => setInsertMultiJson(INSERT_MULTI_TEMPLATE)}
                className="frost-text-muted hover:text-frost-text cursor-pointer text-xs"
              >
                Reset example
              </button>
            }
          >
            <JsonBox value={insertMultiJson} onChange={setInsertMultiJson} rows={14} />
          </Step>
        )}

        {selectedOperation === 'update-multi' && (
          <Step
            number={nextStep()}
            title="Tables and changes"
            hint='One entry per table: "table_name", a "filter" for its rows, and the new values in "data".'
            action={
              <button
                type="button"
                onClick={() => setUpdateMultiJson(UPDATE_MULTI_TEMPLATE)}
                className="frost-text-muted hover:text-frost-text cursor-pointer text-xs"
              >
                Reset example
              </button>
            }
          >
            <JsonBox value={updateMultiJson} onChange={setUpdateMultiJson} rows={14} />
            <label className="frost-text flex cursor-pointer items-start gap-2.5 text-sm">
              <Checkbox
                checked={requireAllMatched}
                onCheckedChange={(checked) => setRequireAllMatched(checked === true)}
                className="mt-0.5"
              />
              <span>
                Every filter must match a row
                <span className="frost-text-muted block text-xs">
                  If any entry matches nothing, nothing changes. Turn off to update whatever does match.
                </span>
              </span>
            </label>
          </Step>
        )}
      </div>

      <div className="border-frost-border mt-auto flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3.5">
        <p
          className={cn(
            'flex min-w-0 items-center gap-1.5 text-xs',
            problems.length ? 'text-amber-600 dark:text-amber-400' : 'frost-text-muted'
          )}
        >
          {problems.length ? (
            <>
              <CircleAlert className="size-3.5 shrink-0" />
              <span className="truncate">{problems[0]}</span>
            </>
          ) : operation.destructive ? (
            'You’ll be asked to confirm.'
          ) : (
            'Ready to run.'
          )}
        </p>
        <Button
          variant={operation.destructive ? 'destructive' : 'default'}
          onClick={handleRun}
          loading={running}
          disabled={running || problems.length > 0}
        >
          {operation.destructive ? <operation.icon className="size-4" /> : <Play className="size-4" />}
          {operation.runLabel}
        </Button>
      </div>
    </div>
  );
};

export default OperationForm;
