import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import FieldHelp from '@app/components/FieldHelp';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import { cn } from '@app/lib/utils';
import { extractErrorMessage } from '@app/lib/errors';
import { useNotifyStore } from '@app/store';
import { Columns3, History, Keyboard, Maximize2, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import DatasourceActivity from './DatasourceActivity';
import { rowKeyFilter } from './odata-filter';
import { formatCellValue, recordColumns, SortState } from './records';
import RecordsTable from './RecordsTable';

// Columns that usually identify a row, tried in order when picking the key for edits and deletes.
const KEY_CANDIDATES = ['id', 'uuid', '_id'];

type RowDialog =
  | { kind: 'insert' }
  | { kind: 'edit'; row: Record<string, unknown> }
  | { kind: 'delete'; row: Record<string, unknown> }
  | { kind: 'history'; row: Record<string, unknown> }
  | { kind: 'details'; row: Record<string, unknown> }
  | null;

const Kbd = ({ children }: { children: React.ReactNode }) => (
  <kbd className="border-frost-border bg-frost-glass rounded border px-1 font-mono text-[11px] leading-4">
    {children}
  </kbd>
);

/** Compares two cell values for a client-side sort: numbers as numbers, everything else as text. */
const compareValues = (a: unknown, b: unknown) => {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return formatCellValue(a).localeCompare(formatCellValue(b), undefined, { numeric: true, sensitivity: 'base' });
};

interface RowsWorkspaceProps {
  /** Needed for edits, deletes, inserts and history; read-only rows can leave it out. */
  datasourceId?: string;
  /** The table the rows came from, which edits, deletes, inserts and history act on; for read-only rows, a name. */
  table: string;
  /**
   * Rows that don't map back to one table, such as a dynamic query's result: no edit, delete, history or insert,
   * and the key column only decides which column stays pinned on the left.
   */
  readOnly?: boolean;
  rows: Record<string, unknown>[];
  /** Shown instead of the table while loading, on error or when there are no rows. */
  status?: React.ReactNode;
  /** Sorting done by the server. Without it, headers sort the rows already here. */
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  /** Called after an insert, edit or delete so the rows can be fetched again. */
  onChanged?: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  /** The left end of the toolbar, e.g. the table name or a result count. */
  title: React.ReactNode;
  /** More toolbar buttons, placed before Expand and Insert, e.g. a filter toggle. */
  toolbarExtras?: React.ReactNode;
  /** A panel between the toolbar and the rows, e.g. an open filter. */
  belowToolbar?: React.ReactNode;
  /** The left of the footer, e.g. "Rows 1–25". */
  footerLabel?: React.ReactNode;
  /** The right of the footer, e.g. page controls. */
  footerEnd?: React.ReactNode;
  /** A line under the expanded view's title, e.g. the filter in use. */
  expandedSubtitle?: React.ReactNode;
  allowInsert?: boolean;
  className?: string;
}

/**
 * Rows from one table with everything for reading and changing them: a row key to find rows by, a column
 * chooser, a larger expanded view, a row's full details, and edit, delete, history and insert. The Data tab and
 * the Operations results both use it, so the two behave the same.
 */
const RowsWorkspace: React.FC<RowsWorkspaceProps> = ({
  datasourceId,
  table,
  rows,
  status,
  sort: serverSort,
  onSortChange,
  onChanged,
  onRefresh,
  refreshing,
  title,
  toolbarExtras,
  belowToolbar,
  footerLabel,
  footerEnd,
  expandedSubtitle,
  allowInsert = true,
  readOnly = false,
  className,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [keyColumn, setKeyColumn] = useState('');
  const [hiddenColumns, setHiddenColumns] = useState<string[]>([]);
  const [columnSearch, setColumnSearch] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [localSort, setLocalSort] = useState<SortState>(null);
  const [dialog, setDialog] = useState<RowDialog>(null);
  const [dialogJson, setDialogJson] = useState('');
  const [saving, setSaving] = useState(false);

  const columns = useMemo(() => recordColumns(rows), [rows]);

  // A different table starts with its own key, every column showing and no local sort.
  useEffect(() => {
    setKeyColumn('');
    setHiddenColumns([]);
    setLocalSort(null);
  }, [table]);

  // Default the key to an id-like column, keeping the user's pick while it still exists.
  useEffect(() => {
    if (columns.length === 0 || columns.includes(keyColumn)) return;
    setKeyColumn(KEY_CANDIDATES.find((candidate) => columns.includes(candidate)) ?? columns[0]);
  }, [columns, keyColumn]);

  const sort = onSortChange ? serverSort : localSort;
  const shownRows = useMemo(() => {
    if (onSortChange || !localSort) return rows;
    const direction = localSort.direction === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => compareValues(a[localSort.column], b[localSort.column]) * direction);
  }, [rows, localSort, onSortChange]);

  const keyMissing = (row: Record<string, unknown>) => row[keyColumn] === null || row[keyColumn] === undefined;

  const toggleColumn = (column: string) =>
    setHiddenColumns((hidden) =>
      hidden.includes(column) ? hidden.filter((name) => name !== column) : [...hidden, column]
    );

  const openDialog = (next: RowDialog) => {
    setDialog(next);
    if (next?.kind === 'insert') {
      // Start from the columns already seen, minus the key the database usually fills in itself.
      const template = Object.fromEntries(
        columns.filter((column) => column !== keyColumn).map((column) => [column, ''])
      );
      setDialogJson(JSON.stringify(template, null, 2));
    } else if (next?.kind === 'edit') {
      setDialogJson(JSON.stringify(next.row, null, 2));
    }
  };

  const mutate = async (call: () => Promise<string | undefined>, fallback: string, failure: string) => {
    setSaving(true);
    try {
      notifySuccess((await call()) || fallback);
      setDialog(null);
      onChanged?.();
    } catch (error) {
      notifyError(extractErrorMessage(error) || failure);
    } finally {
      setSaving(false);
    }
  };

  const parseDialogJson = (): Record<string, unknown> | null => {
    try {
      const value = JSON.parse(dialogJson);
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) return value;
    } catch {
      // Reported below.
    }
    notifyError('Enter the row as a JSON object of column names to values');
    return null;
  };

  const handleInsert = () => {
    const row = parseDialogJson();
    if (!row) return;
    void mutate(
      async () =>
        (await floConsoleService.datasourcesService.insertDatasourceResourceRows(datasourceId!, table, [row])).data
          ?.data?.message,
      'Row inserted',
      'Failed to insert the row'
    );
  };

  const handleEdit = (original: Record<string, unknown>) => {
    const edited = parseDialogJson();
    if (!edited) return;
    // Send only what changed, so columns nobody touched keep their exact stored values.
    const changes = Object.fromEntries(
      Object.entries(edited).filter(([column, value]) => JSON.stringify(value) !== JSON.stringify(original[column]))
    );
    if (Object.keys(changes).length === 0) {
      notifyError('Nothing has changed');
      return;
    }
    void mutate(
      async () =>
        (
          await floConsoleService.datasourcesService.updateDatasourceResourceRows(
            datasourceId!,
            table,
            rowKeyFilter(keyColumn, original[keyColumn]),
            changes
          )
        ).data?.data?.message,
      'Row updated',
      'Failed to update the row'
    );
  };

  const handleDelete = (row: Record<string, unknown>) =>
    mutate(
      async () =>
        (
          await floConsoleService.datasourcesService.deleteDatasourceResourceRows(
            datasourceId!,
            table,
            rowKeyFilter(keyColumn, row[keyColumn])
          )
        ).data?.data?.message,
      'Row deleted',
      'Failed to delete the row'
    );

  const refreshButton = onRefresh ? (
    <Button variant="outline" size="sm" title="Reload rows" onClick={onRefresh} disabled={refreshing}>
      <RefreshCw className={cn('size-4', refreshing && 'animate-spin')} />
    </Button>
  ) : null;

  // The rows and the footer, shown in the panel and again, larger, in the expanded view.
  const rowsBody = (
    <div className="flex min-h-0 flex-1 flex-col p-4">
      {status ?? (
        <RecordsTable
          records={shownRows}
          sort={sort}
          onSortChange={onSortChange ?? setLocalSort}
          className="flex-1"
          hiddenColumns={hiddenColumns}
          pinnedColumn={keyColumn}
          onRowClick={(row) => openDialog({ kind: 'details', row })}
          rowActions={
            readOnly
              ? undefined
              : (row) => (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      title={keyMissing(row) ? `No ${keyColumn} to find this row by` : 'Edit row'}
                      disabled={keyMissing(row)}
                      onClick={() => openDialog({ kind: 'edit', row })}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Row history"
                      disabled={keyMissing(row)}
                      onClick={() => openDialog({ kind: 'history', row })}
                    >
                      <History className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title={keyMissing(row) ? `No ${keyColumn} to find this row by` : 'Delete row'}
                      disabled={keyMissing(row)}
                      onClick={() => openDialog({ kind: 'delete', row })}
                    >
                      <Trash2 className="size-3.5 text-red-600" />
                    </Button>
                  </>
                )
          }
        />
      )}
    </div>
  );

  const footer = (
    <div className="border-frost-border frost-text-muted flex shrink-0 flex-wrap items-center justify-between gap-3 border-t px-4 py-2.5 text-sm">
      <div className="flex min-w-0 items-center gap-4">
        {footerLabel ? <span className="tabular-nums">{footerLabel}</span> : null}
        {/* Keyboards only: a phone scrolls the table by touch. */}
        {!status && rows.length > 0 && (
          <span className="hidden items-center gap-1.5 text-xs md:inline-flex">
            <Keyboard className="size-3.5" />
            Click the table, then
            <Kbd>←</Kbd>
            <Kbd>→</Kbd>
            to scroll
            <FieldHelp ariaLabel="Keyboard shortcuts for the table" side="top">
              <p className="mb-1.5 font-medium">Scrolling the table</p>
              <ul className="space-y-1">
                <li>
                  <Kbd>←</Kbd> <Kbd>→</Kbd> move sideways a little
                </li>
                <li>
                  <Kbd>Shift</Kbd> + <Kbd>←</Kbd> <Kbd>→</Kbd> move a screen at a time
                </li>
                <li>
                  <Kbd>Home</Kbd> <Kbd>End</Kbd> jump to the first or last column
                </li>
                <li>
                  <Kbd>↑</Kbd> <Kbd>↓</Kbd> scroll up and down
                </li>
              </ul>
              <p className="mt-1.5">Click the table or Tab to it first; a blue outline shows it&apos;s ready.</p>
            </FieldHelp>
          </span>
        )}
      </div>
      {footerEnd ? <div className="flex items-center gap-2">{footerEnd}</div> : null}
    </div>
  );

  return (
    <div
      className={cn(
        'frost-panel ring-frost-border flex min-h-0 flex-col overflow-hidden rounded-xl border ring-1',
        className
      )}
    >
      <div className="border-frost-border flex shrink-0 flex-wrap items-center gap-2 border-b px-4 py-3">
        <div className="mr-auto min-w-0">{title}</div>
        {columns.length > 0 && (
          <div className="flex items-center gap-1.5">
            <FieldHelp
              ariaLabel={readOnly ? 'What is the pinned column?' : 'What is the row key?'}
              side="bottom"
              contentClassName="max-w-sm"
            >
              {readOnly ? (
                <p>
                  This column stays in view on the left while the others scroll, and names each row in its details. Pick
                  whichever identifies a row best.
                </p>
              ) : (
                <>
                  <p className="font-medium">The column Edit, Delete and History use to find a row.</p>
                  <p className="mt-1.5">
                    Changes are sent as a filter on this column, e.g. <code>{rowKeyFilter(keyColumn || 'id', 42)}</code>
                    . Every row with the same value is affected, so pick a column that is unique for each row.
                  </p>
                  <p className="mt-1.5">
                    It starts on id, uuid or _id when the table has one, and stays pinned on the left of the table. Rows
                    with no value in it can&apos;t be edited or deleted here.
                  </p>
                </>
              )}
            </FieldHelp>
            <Select value={keyColumn} onValueChange={setKeyColumn}>
              <SelectTrigger className="h-9 w-auto max-w-52 gap-1.5 text-xs">
                <span className="frost-text-muted">{readOnly ? 'Pinned:' : 'Row key:'}</span>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {columns.map((column) => (
                  <SelectItem key={column} value={column}>
                    {column}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <Popover onOpenChange={(open) => !open && setColumnSearch('')}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" disabled={columns.length === 0} title="Choose which columns to show">
              <Columns3 className="size-4" />
              Columns
              {hiddenColumns.length > 0 ? (
                <span className="frost-text-muted text-xs tabular-nums">
                  {columns.length - hiddenColumns.length}/{columns.length}
                </span>
              ) : null}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="frost-dialog border-frost-border w-64 p-2">
            <Input
              value={columnSearch}
              onChange={(e) => setColumnSearch(e.target.value)}
              placeholder="Find a column"
              aria-label="Find a column"
              className="mb-2 h-8 text-xs"
            />
            <div className="flex max-h-64 flex-col overflow-y-auto">
              {columns
                .filter((column) => column.toLowerCase().includes(columnSearch.trim().toLowerCase()))
                .map((column) => (
                  <label
                    key={column}
                    className="hover:bg-frost-glass flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5"
                  >
                    <Checkbox checked={!hiddenColumns.includes(column)} onCheckedChange={() => toggleColumn(column)} />
                    <span className="frost-text min-w-0 truncate font-mono text-xs">{column}</span>
                    {column === keyColumn ? (
                      <span className="frost-text-subtle ml-auto shrink-0 text-[10px]">key</span>
                    ) : null}
                  </label>
                ))}
            </div>
            <div className="border-frost-border mt-2 flex justify-between border-t pt-2">
              <Button variant="ghost" size="sm" onClick={() => setHiddenColumns([])}>
                Show all
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setHiddenColumns(columns.filter((column) => column !== keyColumn))}
              >
                Only key
              </Button>
            </div>
          </PopoverContent>
        </Popover>
        {toolbarExtras}
        {refreshButton}
        <Button
          variant="outline"
          size="sm"
          title="Open the table in a larger view"
          aria-label="Expand table"
          onClick={() => setExpanded(true)}
          disabled={!table}
        >
          <Maximize2 className="size-4" />
        </Button>
        {allowInsert && !readOnly ? (
          <Button size="sm" onClick={() => openDialog({ kind: 'insert' })} disabled={!table}>
            <Plus className="size-4" />
            Insert row
          </Button>
        ) : null}
      </div>

      {belowToolbar}

      {rowsBody}

      {table ? footer : null}

      {/* The same rows, sort, pages and row actions with most of the screen to show wide tables in. */}
      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="flex h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:h-[92dvh] sm:w-[96vw] sm:max-w-[96vw] sm:p-0">
          <DialogHeader className="border-frost-border flex-row items-center gap-3 space-y-0 border-b px-5 py-3 pr-12">
            <DialogTitle className="min-w-0 truncate font-mono text-base">{table}</DialogTitle>
            {expandedSubtitle ? (
              <span className="frost-text-muted min-w-0 truncate font-mono text-xs">{expandedSubtitle}</span>
            ) : null}
            {refreshButton ? <div className="ml-auto">{refreshButton}</div> : null}
          </DialogHeader>
          {rowsBody}
          {table ? footer : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog?.kind === 'insert' || dialog?.kind === 'edit'}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{dialog?.kind === 'edit' ? 'Edit row' : `Insert a row into ${table}`}</DialogTitle>
          </DialogHeader>
          <Textarea
            value={dialogJson}
            onChange={(e) => setDialogJson(e.target.value)}
            spellCheck={false}
            className="min-h-72 font-mono text-xs leading-relaxed"
          />
          <p className="frost-text-muted text-xs">
            {dialog?.kind === 'edit'
              ? `Only the columns you change are saved. The row is found by ${keyColumn}.`
              : 'One JSON object of column names to values. Leave out columns the database fills in.'}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              loading={saving}
              onClick={() => (dialog?.kind === 'edit' ? handleEdit(dialog.row) : handleInsert())}
            >
              {dialog?.kind === 'edit' ? 'Save' : 'Insert'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {dialog?.kind === 'delete' && (
        <DeleteConfirmationDialog
          isOpen
          title="Delete row"
          message={`Delete the row where ${rowKeyFilter(keyColumn, dialog.row[keyColumn])} from "${table}"? This cannot be undone.`}
          onConfirm={() => void handleDelete(dialog.row)}
          onCancel={() => setDialog(null)}
          loading={saving}
        />
      )}

      {/* One row read top to bottom, column by column: the easy way through a table too wide to scan. */}
      <Dialog open={dialog?.kind === 'details'} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col">
          <DialogHeader>
            <DialogTitle className="font-mono text-base">
              {keyColumn} {dialog?.kind === 'details' ? formatCellValue(dialog.row[keyColumn]) : ''}
            </DialogTitle>
          </DialogHeader>
          {dialog?.kind === 'details' && (
            <>
              <dl className="divide-frost-border -mx-1 min-h-0 flex-1 divide-y overflow-y-auto px-1">
                {recordColumns([dialog.row]).map((column) => {
                  const value = dialog.row[column];
                  return (
                    <div key={column} className="grid gap-1 py-2.5 sm:grid-cols-[minmax(0,180px)_1fr] sm:gap-4">
                      <dt className="frost-text-muted truncate font-mono text-xs" title={column}>
                        {column}
                      </dt>
                      <dd className="frost-text min-w-0 font-mono text-xs break-words whitespace-pre-wrap">
                        {typeof value === 'object' && value !== null
                          ? JSON.stringify(value, null, 2)
                          : formatCellValue(value)}
                      </dd>
                    </div>
                  );
                })}
              </dl>
              {readOnly ? null : (
                <DialogFooter>
                  <Button
                    variant="outline"
                    disabled={keyMissing(dialog.row)}
                    onClick={() => openDialog({ kind: 'history', row: dialog.row })}
                  >
                    <History className="size-4" />
                    History
                  </Button>
                  <Button
                    disabled={keyMissing(dialog.row)}
                    onClick={() => openDialog({ kind: 'edit', row: dialog.row })}
                  >
                    <Pencil className="size-4" />
                    Edit
                  </Button>
                </DialogFooter>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={dialog?.kind === 'history'} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent className="flex max-h-[85vh] max-w-5xl flex-col">
          <DialogHeader>
            <DialogTitle>
              History of {keyColumn} {dialog?.kind === 'history' ? String(dialog.row[keyColumn]) : ''}
            </DialogTitle>
          </DialogHeader>
          <p className="frost-text-muted -mt-2 text-xs">
            Changes that named this row by {keyColumn}. A change that found it by another column won&apos;t show here.
          </p>
          {dialog?.kind === 'history' && (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <DatasourceActivity
                datasourceId={datasourceId!}
                table={table}
                rowParams={{ [keyColumn]: String(dialog.row[keyColumn]) }}
              />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RowsWorkspace;
