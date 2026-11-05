import floConsoleService from '@app/api';
import { copyToClipboard } from '@app/utils/clipboard';
import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { DatasourceTableInsert, DatasourceTableUpdate, GetDatasourceResourceParams } from '@app/types/datasource';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useParams } from 'react-router';
import { recordColumns } from './records';
import { pairsToRow, ValuePair } from './values';
import {
  OperationId,
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
import { useGetDatasourceResources } from '@app/hooks';

/**
 * State and actions for the datasource operations panel: the chosen operation and its inputs, what's wrong
 * with them, the API request they make, and running it (with a preview for updates and deletes).
 */
export const useDatasourceOperation = (datasourceId: string) => {
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

  const tablesQuery = useGetDatasourceResources(appId, datasourceId);
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

  return {
    datasourceId,
    selectedOperation,
    running,
    previewing,
    confirmOpen,
    setConfirmOpen,
    result,
    copied,
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
    chooseOperation,
    chooseTable,
    problems,
    request,
    requestText,
    execute,
    handleRun,
    handlePreview,
    rereadRows,
    handleCopyRequest,
  };
};

export type DatasourceOperationState = ReturnType<typeof useDatasourceOperation>;
