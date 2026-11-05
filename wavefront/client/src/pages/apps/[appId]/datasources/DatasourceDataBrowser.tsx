import floConsoleService from '@app/api';
import { ResourceListSkeleton } from '@app/components/ResourceList';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Skeleton } from '@app/components/ui/skeleton';
import { cn } from '@app/lib/utils';
import { extractErrorMessage } from '@app/lib/errors';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, Filter, RefreshCw, Search, Table2, X } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import FilterBuilder from './FilterBuilder';
import { recordColumns, SortState } from './records';
import RowsWorkspace from './RowsWorkspace';
import { useParams } from 'react-router';
import { useGetDatasourceResources } from '@app/hooks';

const PAGE_SIZES = [25, 50, 100];

/** A table browser: pick a table, page through its rows, sort, filter, and insert, edit or delete rows. */
const DatasourceDataBrowser: React.FC<{ datasourceId: string }> = ({ datasourceId }) => {
  const { app: appId } = useParams<{ app: string }>();
  const [tableSearch, setTableSearch] = useState('');
  const [table, setTable] = useState('');
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<SortState>(null);
  const [filterDraft, setFilterDraft] = useState('');
  const [filter, setFilter] = useState('');
  const [showFilter, setShowFilter] = useState(false);

  const tablesQuery = useGetDatasourceResources(appId, datasourceId);
  const tables = useMemo(() => tablesQuery.data ?? [], [tablesQuery.data]);

  // Open the first table once the list arrives.
  useEffect(() => {
    if (!table && tables.length > 0) setTable(tables[0]);
  }, [table, tables]);

  const rowsQuery = useQuery({
    queryKey: ['datasource-rows', datasourceId, table, filter, sort, pageSize, offset],
    queryFn: async () =>
      (
        await floConsoleService.datasourcesService.getDatasourceResourceData(datasourceId, table, {
          limit: pageSize,
          offset,
          $filter: filter || undefined,
          $orderby: sort ? `${sort.column} ${sort.direction}` : undefined,
        })
      ).data?.data?.records ?? [],
    enabled: Boolean(table),
    retry: false,
  });
  const rows = useMemo(() => rowsQuery.data ?? [], [rowsQuery.data]);
  const columns = useMemo(() => recordColumns(rows), [rows]);

  const openTable = (next: string) => {
    setTable(next);
    setOffset(0);
    setSort(null);
    setFilter('');
    setFilterDraft('');
  };

  const filteredTables = tables.filter((name) => name.toLowerCase().includes(tableSearch.trim().toLowerCase()));
  // A full page may have more after it; a short one is the last.
  const hasNextPage = rows.length === pageSize;

  const status = !table ? (
    <p className="frost-text-muted py-10 text-center text-sm">Pick a table to see its rows.</p>
  ) : rowsQuery.isLoading ? (
    <ResourceListSkeleton view="table" count={8} />
  ) : rowsQuery.error ? (
    <p className="py-10 text-center text-sm text-red-500">
      {extractErrorMessage(rowsQuery.error) || 'Failed to load the rows'}
    </p>
  ) : rows.length === 0 ? (
    <p className="frost-text-muted py-10 text-center text-sm">
      {filter ? 'No rows match this filter.' : offset > 0 ? 'No more rows.' : 'This table is empty.'}
    </p>
  ) : undefined;

  return (
    <div className="grid min-h-0 flex-1 gap-6 overflow-hidden lg:grid-cols-[260px_1fr]">
      <div className="frost-panel ring-frost-border flex min-h-0 flex-col overflow-hidden rounded-xl border ring-1 max-lg:max-h-72">
        <div className="border-frost-border flex shrink-0 items-center gap-2 border-b p-2">
          <div className="relative min-w-0 flex-1">
            <Search className="frost-text-subtle pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              placeholder="Search tables"
              aria-label="Search tables"
              className="h-9 pl-9"
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            title="Reload tables"
            onClick={() => void tablesQuery.refetch()}
            disabled={tablesQuery.isFetching}
          >
            <RefreshCw className={cn('size-4', tablesQuery.isFetching && 'animate-spin')} />
          </Button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-2">
          {tablesQuery.isLoading ? (
            Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} className="mx-1 my-1.5 h-5" />)
          ) : tablesQuery.error ? (
            <p className="p-3 text-sm text-red-500">
              {extractErrorMessage(tablesQuery.error) || 'Failed to load the tables'}
            </p>
          ) : filteredTables.length === 0 ? (
            <p className="frost-text-muted p-3 text-sm">No tables found.</p>
          ) : (
            filteredTables.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => openTable(name)}
                title={name}
                className={cn(
                  'flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left font-mono text-xs transition-colors',
                  table === name
                    ? 'bg-frost-dialog frost-text font-medium'
                    : 'frost-text-muted hover:bg-frost-dialog/60'
                )}
              >
                <Table2 className="size-3.5 shrink-0 opacity-70" />
                <span className="truncate">{name}</span>
              </button>
            ))
          )}
        </div>
      </div>

      <RowsWorkspace
        datasourceId={datasourceId}
        table={table}
        rows={rows}
        status={status}
        sort={sort}
        onSortChange={(next) => {
          setSort(next);
          setOffset(0);
        }}
        onChanged={() => void rowsQuery.refetch()}
        onRefresh={() => void rowsQuery.refetch()}
        refreshing={rowsQuery.isFetching}
        title={
          <h2 className="frost-text min-w-0 truncate font-mono text-sm font-semibold">{table || 'Pick a table'}</h2>
        }
        // Pressed while the panel is open; the dot means a filter is narrowing the rows, open or not.
        toolbarExtras={
          <Button
            variant="outline"
            size="sm"
            aria-pressed={showFilter}
            aria-expanded={showFilter}
            onClick={() => setShowFilter((open) => !open)}
            disabled={!table}
            className={cn(showFilter && 'bg-brand/12 text-brand ring-brand/30 hover:bg-brand/15 border-transparent')}
          >
            <Filter className="size-4" />
            Filter
            {filter ? <span aria-label="Filter applied" className="bg-brand size-1.5 rounded-full" /> : null}
            <ChevronDown className={cn('size-3.5 transition-transform', showFilter && 'rotate-180')} />
          </Button>
        }
        belowToolbar={
          <>
            {showFilter && table && (
              <div className="border-frost-border bg-frost-glass/40 flex shrink-0 flex-col gap-3 border-b px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="frost-text min-w-0 truncate text-xs font-semibold">
                    Filter rows
                    {filter ? (
                      <span className="frost-text-muted ml-2 font-mono font-normal" title={filter}>
                        Applied: {filter}
                      </span>
                    ) : null}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Close filter"
                    title="Close (the applied filter stays)"
                    onClick={() => setShowFilter(false)}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
                <FilterBuilder
                  columns={columns}
                  value={filterDraft}
                  onChange={setFilterDraft}
                  placeholder="e.g. status eq 'active' $and amount gte 100"
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      setFilter(filterDraft.trim());
                      setOffset(0);
                    }}
                  >
                    Apply
                  </Button>
                  {filter && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setFilter('');
                        setFilterDraft('');
                        setOffset(0);
                      }}
                    >
                      Clear
                    </Button>
                  )}
                </div>
              </div>
            )}
          </>
        }
        footerLabel={rows.length > 0 ? `Rows ${offset + 1}–${offset + rows.length}` : 'No rows'}
        footerEnd={
          <>
            <Select
              value={String(pageSize)}
              onValueChange={(value) => {
                setPageSize(Number(value));
                setOffset(0);
              }}
            >
              <SelectTrigger className="h-8 w-auto gap-1.5 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size} per page
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0 || rowsQuery.isFetching}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasNextPage || rowsQuery.isFetching}
              onClick={() => setOffset(offset + pageSize)}
            >
              Next
            </Button>
          </>
        }
        expandedSubtitle={filter ? <span title={filter}>Filtered: {filter}</span> : undefined}
      />
    </div>
  );
};

export default DatasourceDataBrowser;
