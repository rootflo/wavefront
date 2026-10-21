import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import React, { useMemo, useState } from 'react';

type OperationId = 'get-table-names' | 'get-table-data' | 'delete-rows';

const OPERATIONS: { id: OperationId; label: string; description: string }[] = [
  {
    id: 'get-table-names',
    label: 'Get table names',
    description: 'List all tables available in this datasource.',
  },
  {
    id: 'get-table-data',
    label: 'Get table data',
    description: 'Fetch rows from a selected table with optional limit and offset.',
  },
  {
    id: 'delete-rows',
    label: 'Delete rows',
    description: 'Delete rows from a table that match an OData filter.',
  },
];

interface DatasourceOperationsProps {
  datasourceId: string;
}

const formatCellValue = (value: unknown): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const DatasourceOperations: React.FC<DatasourceOperationsProps> = ({ datasourceId }) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const [selectedOperation, setSelectedOperation] = useState<OperationId>('get-table-names');
  const [loading, setLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const [tableNames, setTableNames] = useState<string[]>([]);
  const [selectedTable, setSelectedTable] = useState('');
  const [limit, setLimit] = useState('10');
  const [offset, setOffset] = useState('0');
  const [deleteFilter, setDeleteFilter] = useState('');
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [deleteResult, setDeleteResult] = useState<string | null>(null);

  const columns = useMemo(() => {
    if (records.length === 0) return [];
    const keys = new Set<string>();
    records.forEach((row) => {
      Object.keys(row).forEach((key) => keys.add(key));
    });
    return Array.from(keys);
  }, [records]);

  const fetchTableNames = async (): Promise<string[]> => {
    const response = await floConsoleService.datasourcesService.getDatasourceResources(datasourceId);
    const resources = response.data?.data?.resources ?? [];
    setTableNames(resources);
    if (resources.length > 0 && !selectedTable) {
      setSelectedTable(resources[0]);
    }
    return resources;
  };

  const handleGetTableNames = async () => {
    setLoading(true);
    setRecords([]);
    setDeleteResult(null);
    try {
      const resources = await fetchTableNames();
      notifySuccess(`Fetched ${resources.length} table${resources.length === 1 ? '' : 's'}`);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to fetch table names');
    } finally {
      setLoading(false);
    }
  };

  const handleGetTableData = async () => {
    if (!selectedTable) {
      notifyError('Select a table first');
      return;
    }

    const parsedLimit = Number(limit);
    const parsedOffset = Number(offset);
    if (!Number.isInteger(parsedLimit) || parsedLimit < 1) {
      notifyError('Limit must be a positive integer');
      return;
    }
    if (!Number.isInteger(parsedOffset) || parsedOffset < 0) {
      notifyError('Offset must be a non-negative integer');
      return;
    }

    setLoading(true);
    setDeleteResult(null);
    try {
      if (tableNames.length === 0) {
        await fetchTableNames();
      }

      const response = await floConsoleService.datasourcesService.getDatasourceResourceData(
        datasourceId,
        selectedTable,
        { limit: parsedLimit, offset: parsedOffset }
      );
      const nextRecords = response.data?.data?.records ?? [];
      setRecords(nextRecords);
      notifySuccess(`Fetched ${nextRecords.length} row${nextRecords.length === 1 ? '' : 's'}`);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to fetch table data');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRows = async () => {
    if (!selectedTable) {
      notifyError('Select a table first');
      return;
    }
    if (!deleteFilter.trim()) {
      notifyError('A non-empty filter is required to delete rows');
      return;
    }

    setLoading(true);
    setRecords([]);
    try {
      const response = await floConsoleService.datasourcesService.deleteDatasourceResourceRows(
        datasourceId,
        selectedTable,
        deleteFilter.trim()
      );
      const deletedRows = response.data?.data?.deleted_rows ?? 0;
      const message =
        response.data?.data?.message || `Deleted ${deletedRows} row${deletedRows === 1 ? '' : 's'} successfully`;
      setDeleteResult(message);
      notifySuccess(message);
      setShowDeleteConfirm(false);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to delete rows');
    } finally {
      setLoading(false);
    }
  };

  const handleRun = async () => {
    if (selectedOperation === 'get-table-names') {
      await handleGetTableNames();
      return;
    }
    if (selectedOperation === 'get-table-data') {
      await handleGetTableData();
      return;
    }
    if (!selectedTable) {
      notifyError('Select a table first');
      return;
    }
    if (!deleteFilter.trim()) {
      notifyError('A non-empty filter is required to delete rows');
      return;
    }
    setShowDeleteConfirm(true);
  };

  const handleLoadTablesForSelect = async () => {
    if (tableNames.length > 0 || loading) return;
    setLoading(true);
    try {
      await fetchTableNames();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to fetch table names');
    } finally {
      setLoading(false);
    }
  };

  const showTableSelect = selectedOperation === 'get-table-data' || selectedOperation === 'delete-rows';

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="grid min-h-0 flex-1 gap-6 overflow-hidden lg:grid-cols-[280px_1fr]">
        <div className="frost-panel ring-frost-border flex min-h-0 flex-col overflow-hidden rounded-xl border ring-1">
          <div className="shrink-0 border-b border-[#EFF0F1] px-4 py-3">
            <h2 className="frost-text text-sm font-semibold">Operations</h2>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
            {OPERATIONS.map((operation) => {
              const isActive = selectedOperation === operation.id;
              return (
                <button
                  key={operation.id}
                  type="button"
                  onClick={() => {
                    setSelectedOperation(operation.id);
                    setDeleteResult(null);
                  }}
                  className={`rounded-lg px-3 py-2.5 text-left transition-colors ${
                    isActive ? 'bg-frost-dialog frost-text font-medium' : 'frost-text-muted hover:bg-frost-dialog/60'
                  }`}
                >
                  <p className="text-sm">{operation.label}</p>
                  <p className="mt-0.5 text-xs opacity-80">{operation.description}</p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="frost-panel ring-frost-border flex min-h-0 flex-col overflow-hidden rounded-xl border ring-1">
          <div className="flex shrink-0 items-center justify-between gap-4 border-b border-[#EFF0F1] px-4 py-3">
            <div className="min-w-0">
              <h2 className="frost-text text-sm font-semibold">
                {OPERATIONS.find((op) => op.id === selectedOperation)?.label}
              </h2>
              <p className="frost-text-muted mt-0.5 text-xs">
                {OPERATIONS.find((op) => op.id === selectedOperation)?.description}
              </p>
            </div>
            <Button
              className="shrink-0"
              variant={selectedOperation === 'delete-rows' ? 'destructive' : 'default'}
              onClick={() => void handleRun()}
              loading={loading}
              disabled={loading}
            >
              {selectedOperation === 'delete-rows' ? 'Delete' : 'Run'}
            </Button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4">
            {showTableSelect && (
              <div
                className={`grid shrink-0 gap-4 ${
                  selectedOperation === 'get-table-data' ? 'md:grid-cols-3' : 'md:grid-cols-1'
                }`}
              >
                <div className="space-y-2">
                  <Label>Table</Label>
                  <Select
                    value={selectedTable}
                    onValueChange={setSelectedTable}
                    onOpenChange={(open) => {
                      if (open) void handleLoadTablesForSelect();
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a table" />
                    </SelectTrigger>
                    <SelectContent>
                      {tableNames.map((tableName) => (
                        <SelectItem key={tableName} value={tableName}>
                          {tableName}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedOperation === 'get-table-data' && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="operations-limit">Limit</Label>
                      <Input
                        id="operations-limit"
                        type="number"
                        min={1}
                        value={limit}
                        onChange={(e) => setLimit(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="operations-offset">Offset</Label>
                      <Input
                        id="operations-offset"
                        type="number"
                        min={0}
                        value={offset}
                        onChange={(e) => setOffset(e.target.value)}
                      />
                    </div>
                  </>
                )}
              </div>
            )}

            {selectedOperation === 'delete-rows' && (
              <div className="shrink-0 space-y-2">
                <Label htmlFor="operations-delete-filter">Filter</Label>
                <Input
                  id="operations-delete-filter"
                  value={deleteFilter}
                  onChange={(e) => setDeleteFilter(e.target.value)}
                  placeholder="e.g. loan_id eq '1234'"
                />
                <p className="frost-text-muted text-xs">
                  OData filter matching rows to delete. A non-empty filter is required.
                </p>
              </div>
            )}

            {selectedOperation === 'get-table-names' &&
              (tableNames.length === 0 ? (
                <p className="frost-text-muted text-sm">Run the operation to list table names.</p>
              ) : (
                <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-lg border ring-1">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-16">#</TableHead>
                        <TableHead>Table name</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tableNames.map((tableName, index) => (
                        <TableRow key={tableName}>
                          <TableCell className="frost-text-muted">{index + 1}</TableCell>
                          <TableCell className="font-mono text-sm">{tableName}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ))}

            {selectedOperation === 'get-table-data' &&
              (records.length === 0 ? (
                <p className="frost-text-muted text-sm">Run the operation to fetch table rows.</p>
              ) : (
                // Use a plain <table> (not the shared Table wrapper) so width can
                // grow with columns and overflow-x-auto can scroll horizontally.
                <div className="frost-table-panel ring-frost-border relative min-h-0 flex-1 overflow-x-auto overflow-y-auto rounded-lg border ring-1">
                  <table className="w-max min-w-full caption-bottom border-collapse text-sm">
                    <TableHeader>
                      <TableRow>
                        {columns.map((column) => (
                          <TableHead key={column} className="whitespace-nowrap">
                            {column}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {records.map((row, rowIndex) => (
                        <TableRow key={rowIndex}>
                          {columns.map((column) => (
                            <TableCell
                              key={column}
                              className="max-w-[280px] truncate font-mono text-xs whitespace-nowrap"
                              title={formatCellValue(row[column])}
                            >
                              {formatCellValue(row[column])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </table>
                </div>
              ))}

            {selectedOperation === 'delete-rows' && (
              <div className="min-h-0 flex-1">
                {deleteResult ? (
                  <p className="frost-text text-sm">{deleteResult}</p>
                ) : (
                  <p className="frost-text-muted text-sm">Choose a table, enter a filter, then delete matching rows.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {showDeleteConfirm && (
        <DeleteConfirmationDialog
          isOpen={showDeleteConfirm}
          title="Delete rows"
          message={`Delete rows from "${selectedTable}" matching filter: ${deleteFilter.trim()}? This cannot be undone.`}
          onConfirm={() => void handleDeleteRows()}
          onCancel={() => setShowDeleteConfirm(false)}
          loading={loading}
          confirmLabel="Delete"
          cancelLabel="Cancel"
        />
      )}
    </div>
  );
};

export default DatasourceOperations;
