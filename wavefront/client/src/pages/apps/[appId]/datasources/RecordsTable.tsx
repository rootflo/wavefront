import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { cn } from '@app/lib/utils';
import { ArrowDown, ArrowUp } from 'lucide-react';
import React, { useMemo } from 'react';
import { formatCellValue, recordColumns, SortState } from './records';

// Cells that stay put while the rest scroll under them need a solid background. The header's z-index and glass
// background come from TableHeader's `[&_th]:` rules, which outrank plain classes, hence the `!`.
const PINNED_HEAD = 'bg-background! z-20!';
const PINNED_CELL = 'bg-background z-[1]';

interface RecordsTableProps {
  records: Record<string, unknown>[];
  /** Clicking a header cycles ascending, descending, unsorted. Without it headers are plain. */
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  /** Buttons for one row, shown in a column pinned to the right edge. */
  rowActions?: (row: Record<string, unknown>) => React.ReactNode;
  /** Columns left out of the table. */
  hiddenColumns?: string[];
  /** Shown first and kept in view on the left while the rest scrolls, e.g. the row's id. */
  pinnedColumn?: string;
  /** Clicking a row (outside its action buttons) calls this, e.g. to show all of its values. */
  onRowClick?: (row: Record<string, unknown>) => void;
  className?: string;
}

const STEP = 160;

/**
 * Rows of any shape as a table that grows sideways with its columns and scrolls within its box. The box takes
 * focus, so the keyboard can scroll it: arrows step, Shift+arrows move a screenful, Home/End jump to an edge.
 */
const RecordsTable: React.FC<RecordsTableProps> = ({
  records,
  sort,
  onSortChange,
  rowActions,
  hiddenColumns,
  pinnedColumn,
  onRowClick,
  className,
}) => {
  const columns = useMemo(() => {
    const visible = recordColumns(records).filter((column) => !hiddenColumns?.includes(column));
    return pinnedColumn && visible.includes(pinnedColumn)
      ? [pinnedColumn, ...visible.filter((column) => column !== pinnedColumn)]
      : visible;
  }, [records, hiddenColumns, pinnedColumn]);
  const pinned = pinnedColumn && columns[0] === pinnedColumn ? pinnedColumn : null;

  const nextSort = (column: string): SortState => {
    if (sort?.column !== column) return { column, direction: 'asc' };
    return sort.direction === 'asc' ? { column, direction: 'desc' } : null;
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    // Only when the box itself has focus, so arrows inside a header button or row action keep their own meaning.
    if (event.target !== event.currentTarget) return;
    const box = event.currentTarget;
    const page = box.clientWidth * 0.8;
    const moves: Record<string, () => void> = {
      ArrowLeft: () => box.scrollBy({ left: -(event.shiftKey ? page : STEP), behavior: 'smooth' }),
      ArrowRight: () => box.scrollBy({ left: event.shiftKey ? page : STEP, behavior: 'smooth' }),
      Home: () => box.scrollTo({ left: 0, behavior: 'smooth' }),
      End: () => box.scrollTo({ left: box.scrollWidth, behavior: 'smooth' }),
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      move();
    }
  };

  return (
    // A plain <table> (not the shared Table wrapper) so width can grow with columns and the box scrolls sideways.
    <div
      tabIndex={0}
      role="region"
      aria-label="Rows. Use the arrow keys to scroll, Shift with an arrow to move a screen, Home and End for the edges."
      title="Click here, then use ← → to scroll sideways (Shift for a screen, Home/End for the edges)"
      onKeyDown={onKeyDown}
      className={cn(
        'frost-table-panel ring-frost-border focus-visible:ring-brand/40 relative min-h-0 overflow-auto rounded-lg border ring-1 focus-visible:ring-2 focus-visible:outline-none',
        className
      )}
    >
      <table className="w-max min-w-full caption-bottom border-collapse text-sm">
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead
                key={column}
                className={cn(
                  'whitespace-nowrap',
                  column === pinned && cn('border-frost-border left-0 border-r', PINNED_HEAD)
                )}
              >
                {onSortChange ? (
                  <button
                    type="button"
                    onClick={() => onSortChange(nextSort(column))}
                    className="hover:text-frost-text inline-flex cursor-pointer items-center gap-1"
                  >
                    {column}
                    {sort?.column === column ? (
                      sort.direction === 'asc' ? (
                        <ArrowUp className="size-3.5" />
                      ) : (
                        <ArrowDown className="size-3.5" />
                      )
                    ) : null}
                  </button>
                ) : (
                  column
                )}
              </TableHead>
            ))}
            {rowActions ? <TableHead className={cn('right-0 w-px', PINNED_HEAD)} /> : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {records.map((row, rowIndex) => (
            <TableRow
              key={rowIndex}
              className={cn('group', onRowClick && 'cursor-pointer')}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <TableCell
                  key={column}
                  className={cn(
                    'max-w-[280px] truncate font-mono text-xs whitespace-nowrap',
                    column === pinned && cn('border-frost-border sticky left-0 border-r', PINNED_CELL)
                  )}
                  title={formatCellValue(row[column])}
                >
                  {formatCellValue(row[column])}
                </TableCell>
              ))}
              {rowActions ? (
                <TableCell
                  className={cn('sticky right-0 py-1 whitespace-nowrap', PINNED_CELL)}
                  onClick={(event) => event.stopPropagation()}
                >
                  <div className="flex items-center justify-end gap-0.5">{rowActions(row)}</div>
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </table>
    </div>
  );
};

export default RecordsTable;
