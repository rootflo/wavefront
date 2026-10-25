import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@app/components/ui/tooltip';
import { cn, copyToClipboard, extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { DatasourceTableInsert, DatasourceTableUpdate, GetDatasourceResourceParams } from '@app/types/datasource';
import { useQuery } from '@tanstack/react-query';
import { Check, CircleAlert, Copy, Eye, Play } from 'lucide-react';
import React, { useState } from 'react';
import { useParams } from 'react-router';
import FilterBuilder from './FilterBuilder';
import { recordColumns } from './records';
import RowsWorkspace from './RowsWorkspace';
import ValuesEditor from './ValuesEditor';
import { pairsToRow, ValuePair } from './values';
import {
  OperationId,
  OPERATION_GROUPS,
  OPERATIONS,
  INSERT_ROWS_TEMPLATE,
  INSERT_MULTI_TEMPLATE,
  UPDATE_MULTI_TEMPLATE,
  PREVIEW_LIMIT,
  Result,
  ApiRequest,
  isPlainObject,
  parseJson,
} from './operations';
import { Step, ModeSwitch, JsonBox } from './OperationParts';

interface DatasourceOperationsProps {
  datasourceId: string;
}

/**
 * Bulk and advanced operations, as a guided flow: pick what to do, fill in the numbered steps, preview what an
 * update or delete will touch, then run it and see the result and the exact API request beside the form.
 */
const DatasourceOperations: React.FC<DatasourceOperationsProps> = ({ datasourceId }) => {
  const { app: appId } = useParams<{ app: string }>();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [selectedOperation, setSelectedOperation] = useState<OperationId>('get-table-data');
  const [running, setRunning] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [result, setResult] = useState<Result>(null);
  const [copied, setCopied] = useState(false);

  const [table, setTable] = useState('');
  const [filter, setFilter] = useState('');
  // Query rows
  const [limit, setLimit] = useState('25');
  const [offset, setOffset] = useState('0');
  const [select, setSelect] = useState('');
  const [orderBy, setOrderBy] = useState('');
  const [groupBy, setGroupBy] = useState('');
  const [expand, setExpand] = useState('');
  const [join, setJoin] = useState('');
  const [showMoreOptions, setShowMoreOptions] = useState(false);
  // Values for insert and update
  const [valuesAsJson, setValuesAsJson] = useState(false);
  const [pairs, setPairs] = useState<ValuePair[]>([{ column: '', value: '' }]);
  const [insertJson, setInsertJson] = useState(INSERT_ROWS_TEMPLATE);
  const [updateJson, setUpdateJson] = useState('{\n  "status": "active"\n}');
  // Transactions
  const [insertMultiJson, setInsertMultiJson] = useState(INSERT_MULTI_TEMPLATE);
  const [updateMultiJson, setUpdateMultiJson] = useState(UPDATE_MULTI_TEMPLATE);
  const [requireAllMatched, setRequireAllMatched] = useState(true);

  const operation = OPERATIONS.find((op) => op.id === selectedOperation)!;

  // Same key as the Data and Info tabs, so the list is fetched once for all three.
  const tablesQuery = useQuery({
    queryKey: ['datasource-tables', datasourceId],
    queryFn: async () =>
      (await floConsoleService.datasourcesService.getDatasourceResources(datasourceId)).data?.data?.resources ?? [],
  });
  const tables = tablesQuery.data ?? [];

  // One sample row tells us the table's columns, for suggestions in the filter and values steps.
  const columnsQuery = useQuery({
    queryKey: ['datasource-columns', datasourceId, table],
    queryFn: async () =>
      recordColumns(
        (await floConsoleService.datasourcesService.getDatasourceResourceData(datasourceId, table, { limit: 1 })).data
          ?.data?.records ?? []
      ),
    enabled: Boolean(table),
    retry: false,
  });
  const columns = columnsQuery.data ?? [];

  const chooseOperation = (id: OperationId) => {
    setSelectedOperation(id);
    setResult(null);
  };

  const chooseTable = (next: string) => {
    setTable(next);
    setFilter('');
    setPairs([{ column: '', value: '' }]);
    setResult(null);
  };

  // ---- Inputs, checked before anything is sent ----

  /** The rows to insert, or why they can't be sent. */
  const insertRows = (): { rows?: Record<string, unknown>[]; error?: string } => {
    if (!valuesAsJson) {
      const row = pairsToRow(pairs);
      return Object.keys(row).length ? { rows: [row] } : { error: 'Add at least one column and its value' };
    }
    const parsed = parseJson(insertJson);
    if (parsed.error) return { error: parsed.error };
    const rows = Array.isArray(parsed.value) ? parsed.value : [parsed.value];
    if (rows.length === 0 || !rows.every(isPlainObject)) return { error: 'Enter a row object, or a list of them' };
    return { rows: rows as Record<string, unknown>[] };
  };

  /** The new values for an update, or why they can't be sent. */
  const updateValues = (): { data?: Record<string, unknown>; error?: string } => {
    if (!valuesAsJson) {
      const row = pairsToRow(pairs);
      return Object.keys(row).length ? { data: row } : { error: 'Add at least one column to change' };
    }
    const parsed = parseJson(updateJson);
    if (parsed.error) return { error: parsed.error };
    if (!isPlainObject(parsed.value) || Object.keys(parsed.value).length === 0) {
      return { error: 'New values must be an object of column names to values' };
    }
    return { data: parsed.value };
  };

  const tableEntries = (text: string, needsFilter: boolean): { entries?: unknown[]; error?: string } => {
    const parsed = parseJson(text);
    if (parsed.error) return { error: parsed.error };
    if (!Array.isArray(parsed.value) || parsed.value.length === 0)
      return { error: 'Enter a list with one entry per table' };
    const bad = parsed.value.findIndex(
      (entry) =>
        !isPlainObject(entry) ||
        typeof entry.table_name !== 'string' ||
        !entry.table_name.trim() ||
        entry.data === undefined ||
        (needsFilter && (typeof entry.filter !== 'string' || !entry.filter.trim()))
    );
    if (bad !== -1) {
      return { error: `Entry ${bad + 1} needs a table_name${needsFilter ? ', a non-empty filter' : ''} and data` };
    }
    return { entries: parsed.value };
  };

  /** Everything wrong with the form for the chosen operation; empty when it can run. */
  const problems = (() => {
    const list: string[] = [];
    if (operation.needsTable && !table) list.push('Pick a table');
    if (operation.needsFilter === 'required' && !filter.trim()) list.push('Add a filter for the rows to change');
    if (selectedOperation === 'get-table-data') {
      if (!Number.isInteger(Number(limit)) || Number(limit) < 1)
        list.push('Rows to fetch must be a whole number above 0');
      if (!Number.isInteger(Number(offset)) || Number(offset) < 0) list.push('Skip must be a whole number, 0 or more');
    }
    if (selectedOperation === 'insert-rows' && table) {
      const { error } = insertRows();
      if (error) list.push(error);
    }
    if (selectedOperation === 'update-rows' && table) {
      const { error } = updateValues();
      if (error) list.push(error);
    }
    if (selectedOperation === 'insert-multi') {
      const { error } = tableEntries(insertMultiJson, false);
      if (error) list.push(error);
    }
    if (selectedOperation === 'update-multi') {
      const { error } = tableEntries(updateMultiJson, true);
      if (error) list.push(error);
    }
    return list;
  })();

  // ---- The request each operation sends, shown in the result panel ----

  const base = `/v1/${appId}/floware/v1/datasources/${datasourceId}/resources`;
  const tablePath = `${base}/${encodeURIComponent(table || '{table}')}`;
  const request: ApiRequest = (() => {
    switch (selectedOperation) {
      case 'get-table-names':
        return { method: 'GET', path: base };
      case 'get-table-data':
        return {
          method: 'GET',
          path: tablePath,
          query: {
            limit,
            offset,
            $select: select.trim() || undefined,
            $filter: filter.trim() || undefined,
            $orderby: orderBy.trim() || undefined,
            $groupby: groupBy.trim() || undefined,
            $expand: expand.trim() || undefined,
            $join: join.trim() || undefined,
          },
        };
      case 'insert-rows':
        return { method: 'POST', path: tablePath, body: { data: insertRows().rows ?? [] } };
      case 'update-rows':
        return { method: 'PATCH', path: tablePath, body: { filter: filter.trim(), data: updateValues().data ?? {} } };
      case 'delete-rows':
        return { method: 'DELETE', path: tablePath, body: { filter: filter.trim() } };
      case 'insert-multi':
        return {
          method: 'POST',
          path: `${base}/insert`,
          body: { inserts: tableEntries(insertMultiJson, false).entries ?? [] },
        };
      case 'update-multi':
        return {
          method: 'PATCH',
          path: `${base}/update`,
          body: { updates: tableEntries(updateMultiJson, true).entries ?? [], require_all_matched: requireAllMatched },
        };
    }
  })();

  const requestText = (() => {
    const query = Object.entries(request.query ?? {})
      .filter(([, value]) => value !== undefined && value !== '')
      .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
      .join('&');
    const line = `${request.method} ${request.path}${query ? `?${query}` : ''}`;
    return request.body === undefined ? line : `${line}\n\n${JSON.stringify(request.body, null, 2)}`;
  })();

  // ---- Running ----

  const fail = (error: unknown, fallback: string) => {
    const text = extractErrorMessage(error) || fallback;
    setResult({ kind: 'message', ok: false, text });
    notifyError(text);
  };

  const succeed = (text: string) => {
    setResult({ kind: 'message', ok: true, text });
    notifySuccess(text);
    // The table's columns may have changed shape; the next suggestions should reflect it.
    void columnsQuery.refetch();
  };

  const execute = async () => {
    const service = floConsoleService.datasourcesService;
    setRunning(true);
    try {
      switch (selectedOperation) {
        case 'get-table-names': {
          const { data } = await tablesQuery.refetch();
          setResult({ kind: 'tables', names: data ?? [] });
          break;
        }
        case 'get-table-data': {
          const query = request.query!;
          const readParams: GetDatasourceResourceParams = {
            limit: Number(limit),
            offset: Number(offset),
            $select: query.$select as string | undefined,
            $filter: query.$filter as string | undefined,
            $orderby: query.$orderby as string | undefined,
            $groupby: query.$groupby as string | undefined,
            $expand: query.$expand as string | undefined,
            $join: query.$join as string | undefined,
          };
          const response = await service.getDatasourceResourceData(datasourceId, table, readParams);
          const records = response.data?.data?.records ?? [];
          setResult({
            kind: 'rows',
            records,
            title: `${records.length} row${records.length === 1 ? '' : 's'}`,
            table,
            params: readParams,
          });
          break;
        }
        case 'insert-rows': {
          const rows = insertRows().rows!;
          const response = await service.insertDatasourceResourceRows(datasourceId, table, rows);
          succeed(response.data?.data?.message || `Inserted ${rows.length} row${rows.length === 1 ? '' : 's'}`);
          break;
        }
        case 'update-rows': {
          const response = await service.updateDatasourceResourceRows(
            datasourceId,
            table,
            filter.trim(),
            updateValues().data!
          );
          succeed(response.data?.data?.message || 'Rows updated');
          break;
        }
        case 'delete-rows': {
          const response = await service.deleteDatasourceResourceRows(datasourceId, table, filter.trim());
          const deleted = response.data?.data?.deleted_rows ?? 0;
          succeed(response.data?.data?.message || `Deleted ${deleted} row${deleted === 1 ? '' : 's'}`);
          break;
        }
        case 'insert-multi': {
          const entries = tableEntries(insertMultiJson, false).entries as DatasourceTableInsert[];
          const response = await service.insertDatasourceRowsMulti(datasourceId, entries);
          succeed(response.data?.data?.message || 'Rows inserted');
          break;
        }
        case 'update-multi': {
          const entries = tableEntries(updateMultiJson, true).entries as DatasourceTableUpdate[];
          const response = await service.updateDatasourceRowsMulti(datasourceId, entries, requireAllMatched);
          succeed(response.data?.data?.message || 'Rows updated');
          break;
        }
      }
      setConfirmOpen(false);
    } catch (error) {
      fail(error, `${operation.label} failed`);
    } finally {
      setRunning(false);
    }
  };

  const handleRun = () => {
    if (problems.length > 0) {
      notifyError(problems[0]);
      return;
    }
    if (operation.destructive) setConfirmOpen(true);
    else void execute();
  };

  /** Fetches the rows an update or delete would touch, without changing anything. */
  const handlePreview = async () => {
    if (!table || !filter.trim()) return;
    setPreviewing(true);
    try {
      const previewParams: GetDatasourceResourceParams = { $filter: filter.trim(), limit: PREVIEW_LIMIT };
      const response = await floConsoleService.datasourcesService.getDatasourceResourceData(
        datasourceId,
        table,
        previewParams
      );
      const records = response.data?.data?.records ?? [];
      setResult({
        kind: 'rows',
        records,
        table,
        params: previewParams,
        title:
          records.length === 0
            ? 'No rows match'
            : `${records.length === PREVIEW_LIMIT ? `${PREVIEW_LIMIT}+` : records.length} matching row${records.length === 1 ? '' : 's'}`,
        note:
          records.length === PREVIEW_LIMIT
            ? `Showing the first ${PREVIEW_LIMIT}; more rows may match and would be ${selectedOperation === 'delete-rows' ? 'deleted' : 'updated'} too.`
            : `These are the rows that would be ${selectedOperation === 'delete-rows' ? 'deleted' : 'updated'}.`,
      });
    } catch (error) {
      fail(error, 'Failed to preview the matching rows');
    } finally {
      setPreviewing(false);
    }
  };

  /** Repeats the read that produced the current rows, e.g. after a row in them was edited or deleted. */
  const rereadRows = async () => {
    if (result?.kind !== 'rows') return;
    setPreviewing(true);
    try {
      const response = await floConsoleService.datasourcesService.getDatasourceResourceData(
        datasourceId,
        result.table,
        result.params
      );
      const records = response.data?.data?.records ?? [];
      setResult({ ...result, records });
    } catch (error) {
      fail(error, 'Failed to reload the rows');
    } finally {
      setPreviewing(false);
    }
  };

  const handleCopyRequest = async () => {
    if (await copyToClipboard(requestText)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  // ---- Layout ----

  let step = 0;
  const nextStep = () => (step += 1);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pb-6">
      {/* What to do */}
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

      <div className="grid min-h-0 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* How */}
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
                    <Input
                      type="number"
                      min={1}
                      value={limit}
                      onChange={(e) => setLimit(e.target.value)}
                      className="h-9"
                    />
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
                        <Input
                          value={join}
                          onChange={(e) => setJoin(e.target.value)}
                          className="h-9 font-mono text-xs"
                        />
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

        {/* What happened */}
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
            <pre className="frost-text max-h-56 overflow-auto p-5 font-mono text-xs whitespace-pre-wrap">
              {requestText}
            </pre>
          </div>
        </div>
      </div>

      {confirmOpen && (
        <DeleteConfirmationDialog
          isOpen={confirmOpen}
          title={operation.label}
          message={
            selectedOperation === 'delete-rows'
              ? `Delete every row in "${table}" where ${filter.trim()}? This cannot be undone.`
              : selectedOperation === 'update-rows'
                ? `Update every row in "${table}" where ${filter.trim()}? Their current values are overwritten.`
                : 'Update rows in every listed table? Their current values are overwritten, all in one transaction.'
          }
          onConfirm={() => void execute()}
          onCancel={() => setConfirmOpen(false)}
          loading={running}
          confirmLabel={selectedOperation === 'delete-rows' ? 'Delete' : 'Update'}
          cancelLabel="Cancel"
        />
      )}
    </div>
  );
};

export default DatasourceOperations;
