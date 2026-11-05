import floConsoleService from '@app/api';
import { FilterSelect } from '@app/components/ListHeader';
import { ResourceListSkeleton } from '@app/components/ResourceList';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { cn } from '@app/lib/utils';
import { extractErrorMessage } from '@app/lib/errors';
import { DatasourceAuditLog, DatasourceAuditOperation } from '@app/types/datasource';
import { useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import dayjs from 'dayjs';
import { ChevronDown, ChevronRight } from 'lucide-react';
import React, { useState } from 'react';

const PAGE_SIZE = 25;
const ALL_OPERATIONS = 'all';

const OPERATION_STYLES: Record<DatasourceAuditOperation, string> = {
  insert: 'bg-emerald-400/15 text-emerald-800 dark:text-emerald-300',
  update: 'bg-sky-400/15 text-sky-800 dark:text-sky-300',
  delete: 'bg-rose-400/15 text-rose-800 dark:text-rose-300',
  upload: 'bg-violet-400/15 text-violet-800 dark:text-violet-300',
  download: 'bg-amber-400/15 text-amber-800 dark:text-amber-300',
};

const OPERATION_OPTIONS: { value: string; label: string }[] = [
  { value: ALL_OPERATIONS, label: 'All' },
  ...(Object.keys(OPERATION_STYLES) as DatasourceAuditOperation[]).map((operation) => ({
    value: operation,
    label: operation.charAt(0).toUpperCase() + operation.slice(1),
  })),
];

const JsonBlock = ({ label, value }: { label: string; value: unknown }) =>
  value === null || value === undefined ? null : (
    <div className="flex min-w-0 flex-col gap-1.5">
      <p className="frost-text-muted text-xs font-medium">{label}</p>
      <pre className="frost-glass border-frost-border frost-text max-h-72 overflow-auto rounded-lg border p-3 font-mono text-xs whitespace-pre-wrap">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );

interface DatasourceActivityProps {
  datasourceId: string;
  /** Pins the list to one table and hides the table filter, e.g. for one row's history. */
  table?: string;
  /** Columns of one row; only changes that named it by these columns are listed. */
  rowParams?: Record<string, string>;
}

/** The datasource's audit trail: who inserted, updated, deleted, uploaded or downloaded what, newest first. */
const DatasourceActivity: React.FC<DatasourceActivityProps> = ({ datasourceId, table, rowParams }) => {
  const [operation, setOperation] = useState(ALL_OPERATIONS);
  const [tableName, setTableName] = useState(table ?? '');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filters = {
    datasource_id: datasourceId,
    operation: operation === ALL_OPERATIONS ? undefined : (operation as DatasourceAuditOperation),
    table_name: tableName.trim() || undefined,
    // Whole days: from the start of the first to the end of the last.
    from_date: fromDate ? dayjs(fromDate).startOf('day').toISOString() : undefined,
    to_date: toDate ? dayjs(toDate).endOf('day').toISOString() : undefined,
    filter_params: rowParams,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ['datasource-audit-logs', filters, offset],
    queryFn: async () => {
      const response = await floConsoleService.datasourcesService.listDatasourceAuditLogs({
        ...filters,
        offset,
        limit: PAGE_SIZE,
      });
      return response.data?.data;
    },
    retry: false,
  });

  // Any filter change starts again from the first page.
  const onFilterChange =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value);
      setOffset(0);
    };

  const forbidden = (error as AxiosError | null)?.response?.status === 403;
  const logs: DatasourceAuditLog[] = data?.logs ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-end gap-3">
        <FilterSelect
          label="Operation"
          value={operation}
          onValueChange={onFilterChange(setOperation)}
          allValue={ALL_OPERATIONS}
          options={OPERATION_OPTIONS}
        />
        {table ? null : (
          <Input
            value={tableName}
            onChange={(e) => onFilterChange(setTableName)(e.target.value)}
            placeholder="Table name"
            aria-label="Table name"
            className="h-10 w-48 rounded-[10px]"
          />
        )}
        <label className="frost-text-muted flex items-center gap-2 text-xs">
          From
          <Input
            type="date"
            value={fromDate}
            onChange={(e) => onFilterChange(setFromDate)(e.target.value)}
            className="h-10 w-40 rounded-[10px]"
          />
        </label>
        <label className="frost-text-muted flex items-center gap-2 text-xs">
          To
          <Input
            type="date"
            value={toDate}
            onChange={(e) => onFilterChange(setToDate)(e.target.value)}
            className="h-10 w-40 rounded-[10px]"
          />
        </label>
      </div>

      {isLoading ? (
        <ResourceListSkeleton view="table" />
      ) : forbidden ? (
        <p className="frost-text-muted py-10 text-center text-sm">
          Only admins can see this datasource&apos;s activity.
        </p>
      ) : error ? (
        <p className="py-10 text-center text-sm text-red-500">
          {extractErrorMessage(error) || 'Failed to load the activity'}
        </p>
      ) : logs.length === 0 ? (
        <p className="frost-text-muted py-10 text-center text-sm">No activity matches these filters.</p>
      ) : (
        <>
          <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>When</TableHead>
                  <TableHead>Operation</TableHead>
                  <TableHead>Table</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Filter</TableHead>
                  <TableHead>User</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => {
                  const expanded = expandedId === log.id;
                  return (
                    <React.Fragment key={log.id}>
                      <TableRow className="cursor-pointer" onClick={() => setExpandedId(expanded ? null : log.id)}>
                        <TableCell className="frost-text-muted">
                          {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                        </TableCell>
                        <TableCell className="text-sm whitespace-nowrap" title={log.created_at}>
                          {dayjs(log.created_at).format('DD MMM YYYY, HH:mm:ss')}
                        </TableCell>
                        <TableCell>
                          <span
                            className={cn(
                              'rounded-full px-2 py-0.5 text-xs font-medium capitalize',
                              OPERATION_STYLES[log.operation]
                            )}
                          >
                            {log.operation}
                          </span>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{log.table_name || '—'}</TableCell>
                        <TableCell className="frost-text-muted tabular-nums">{log.rows_affected ?? '—'}</TableCell>
                        <TableCell className="max-w-[260px] truncate font-mono text-xs" title={log.filter || ''}>
                          {log.filter || '—'}
                        </TableCell>
                        <TableCell
                          className="frost-text-muted max-w-[180px] truncate font-mono text-xs"
                          title={log.user_id || ''}
                        >
                          {log.user_id || '—'}
                        </TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={7} className="whitespace-normal">
                            <div className="grid gap-4 py-2 lg:grid-cols-2">
                              <JsonBlock label="Changes" value={log.changes} />
                              <JsonBlock label="Filter values" value={log.filter_params} />
                              <JsonBlock label="Details" value={log.meta} />
                              <JsonBlock
                                label="Request"
                                value={{ request_id: log.request_id, batch_id: log.batch_id, role_id: log.role_id }}
                              />
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          <div className="frost-text-muted flex shrink-0 items-center justify-between gap-3 text-sm">
            <span className="tabular-nums">
              {offset + 1}–{offset + logs.length} of {total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + logs.length >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default DatasourceActivity;
