import floConsoleService from '@app/api';
import InferencePopup from '@app/components/InferencePopup';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetWorkflowRuns } from '@app/hooks';
import { getWorkflowRunsKey } from '@app/hooks/data/query-keys';
import { WorkflowRun } from '@app/types/workflow';
import { useQueryClient } from '@tanstack/react-query';
import { ColumnDef, flexRender, getCoreRowModel, getPaginationRowModel, useReactTable } from '@tanstack/react-table';
import dayjs from 'dayjs';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

const PAGE_SIZE = 10;

const WorkflowPipelineDetail = () => {
  const { app: appId, workflowPipelineId } = useParams<{
    app: string;
    workflowPipelineId: string;
  }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [pageIndex, setPageIndex] = useState(0);
  const offset = pageIndex * PAGE_SIZE;

  // Inference popup state
  const [isInferencePopupOpen, setIsInferencePopupOpen] = useState(false);

  // Polling state
  const [activeRunIds, setActiveRunIds] = useState<Set<string>>(new Set());
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Output popup state
  const [isOutputPopupOpen, setIsOutputPopupOpen] = useState(false);
  const [selectedRunOutput, setSelectedRunOutput] = useState<unknown>(null);

  // Fetch workflow runs
  const {
    data: runsData,
    isLoading,
    error: runsError,
  } = useGetWorkflowRuns(appId, workflowPipelineId, offset, PAGE_SIZE);

  const workflowRuns = runsData?.workflow_runs || [];
  const totalCount = runsData?.total_count || 0;

  // Update active runs when data changes
  useEffect(() => {
    if (workflowRuns.length > 0) {
      const activeRuns = workflowRuns.filter(
        (run) => run.status === 'in_progress' || run.status === 'pending' || run.status === 'running'
      );
      if (activeRuns.length > 0) {
        const newActiveRunIds = new Set(activeRuns.map((run) => run.id));
        setActiveRunIds((prev) => new Set([...prev, ...newActiveRunIds]));
      }
    }
  }, [workflowRuns]);

  // Poll individual workflow run for status updates
  const pollWorkflowRun = useCallback(
    async (runId: string) => {
      try {
        const response = await floConsoleService.workflowService.getWorkflowRun(runId);
        if (response.data?.data?.workflow_run) {
          const updatedRun = response.data.data.workflow_run;

          // Invalidate the query to refetch
          queryClient.invalidateQueries({
            queryKey: getWorkflowRunsKey(appId || '', workflowPipelineId || '', offset, PAGE_SIZE),
          });

          // If the run is completed or failed, remove it from active runs
          if (updatedRun.status === 'completed' || updatedRun.status === 'failed') {
            setActiveRunIds((prev) => {
              const newSet = new Set(prev);
              newSet.delete(runId);
              return newSet;
            });
          }
        }
      } catch (error) {
        console.error(`Error polling workflow run ${runId}:`, error);
      }
    },
    [appId, workflowPipelineId, offset, queryClient]
  );

  // Start polling for active runs
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    pollingIntervalRef.current = setInterval(() => {
      activeRunIds.forEach((runId) => {
        pollWorkflowRun(runId);
      });
    }, 3000); // Poll every 3 seconds
  }, [activeRunIds, pollWorkflowRun]);

  // Stop polling
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  // Add a new run to active runs and start polling if needed
  const addActiveRun = useCallback((runId: string) => {
    setActiveRunIds((prev) => new Set([...prev, runId]));
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  // Start/stop polling based on active runs
  useEffect(() => {
    if (activeRunIds.size > 0) {
      startPolling();
    } else {
      stopPolling();
    }
  }, [activeRunIds.size, startPolling, stopPolling]);

  const formatDateTime = (dateString: string | null) => {
    if (!dateString) return '-';
    return dayjs(dayjs(dateString).add(5, 'hours').add(30, 'minutes')).format('DD MMM YYYY hh:mm:ss A');
  };

  const formatOutput = (output: unknown) => {
    if (!output) return '-';
    if (typeof output === 'string') return output;
    return JSON.stringify(output, null, 2);
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'in_progress':
      case 'running':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-yellow-100 text-yellow-800';
    }
  };

  const downloadCsv = async () => {
    try {
      if (!appId || !workflowPipelineId) return;
      const response = await floConsoleService.workflowService.getWorkflowRuns(workflowPipelineId, 0, 2000);
      if (!response.data?.data) return;
      const runs = response.data.data.workflow_runs;
      if (!runs || runs.length === 0) return;

      // Helper function to escape CSV values
      const escapeCsvValue = (value: unknown): string => {
        if (value === null || value === undefined) {
          return '';
        }

        let stringValue = '';
        if (typeof value === 'object') {
          stringValue = JSON.stringify(value);
        } else {
          stringValue = String(value);
        }

        if (
          stringValue.includes(',') ||
          stringValue.includes('\n') ||
          stringValue.includes('\r') ||
          stringValue.includes('"')
        ) {
          stringValue = stringValue.replace(/"/g, '""');
          return `"${stringValue}"`;
        }

        return stringValue;
      };

      const allKeys = Object.keys(runs[0]);
      const csvRow: string[][] = [];

      for (const run of runs) {
        const row: string[] = [];
        allKeys.forEach((key) => {
          row.push(escapeCsvValue(run[key as keyof WorkflowRun]));
        });
        csvRow.push(row);
      }

      let csvContent = '';
      csvContent += allKeys.join(',') + '\r\n';
      csvRow.forEach((row) => {
        csvContent += row.join(',') + '\r\n';
      });

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', 'workflow_runs.csv');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
    }
  };

  const handleRowClick = (run: WorkflowRun) => {
    setSelectedRunOutput(run.output);
    setIsOutputPopupOpen(true);
  };

  const columns: ColumnDef<WorkflowRun>[] = [
    {
      accessorKey: 'id',
      header: 'ID',
      cell: ({ row }) => <div className="font-mono text-sm">{row.getValue('id')}</div>,
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.getValue('status') as string;
        return (
          <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${getStatusBadgeClass(status)}`}>
            {status}
          </span>
        );
      },
    },
    {
      accessorKey: 'start_time',
      header: 'Start Time',
      cell: ({ row }) => {
        const startTime = row.getValue('start_time') as string;
        return <div className="text-sm">{formatDateTime(startTime)}</div>;
      },
    },
    {
      accessorKey: 'end_time',
      header: 'End Time',
      cell: ({ row }) => {
        const endTime = row.original.end_time;
        return <div className="text-sm">{formatDateTime(endTime || null)}</div>;
      },
    },
    {
      accessorKey: 'error',
      header: 'Error',
      cell: ({ row }) => {
        const error = row.original.error;
        return (
          <div className="max-w-xs truncate text-sm" title={error || ''}>
            {error || '-'}
          </div>
        );
      },
    },
    {
      accessorKey: 'output',
      header: 'Output',
      cell: ({ row }) => {
        const output = row.original.output;
        const formatted = formatOutput(output);
        return (
          <div className="max-w-xs truncate text-sm" title={formatted}>
            {formatted}
          </div>
        );
      },
    },
  ];

  const table = useReactTable({
    data: workflowRuns,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    pageCount: Math.ceil(totalCount / PAGE_SIZE),
    state: {
      pagination: {
        pageIndex,
        pageSize: PAGE_SIZE,
      },
    },
    onPaginationChange: (updater) => {
      if (typeof updater === 'function') {
        const newPagination = updater({ pageIndex, pageSize: PAGE_SIZE });
        setPageIndex(newPagination.pageIndex);
      }
    },
  });

  const handleRefresh = () => {
    queryClient.invalidateQueries({
      queryKey: getWorkflowRunsKey(appId || '', workflowPipelineId || '', offset, PAGE_SIZE),
    });
  };

  return (
    <div className="p-8">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${appId}/workflows`)}
                className="hover:text-foreground cursor-pointer"
              >
                Workflows
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Pipeline Runs</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-6 flex justify-between gap-4">
        <h2 className="text-2xl font-semibold text-gray-900">Workflow Pipeline Runs</h2>
        <div className="flex items-center gap-2">
          <Button onClick={downloadCsv}>Download as CSV</Button>
          <Button onClick={() => setIsInferencePopupOpen(true)}>Publish To Pipeline</Button>
        </div>
      </div>

      <div className="rounded-lg bg-white shadow">
        <div className="border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Workflow Runs</h2>
        </div>

        {isLoading && workflowRuns.length === 0 ? (
          <div className="p-6 text-center">
            <div className="text-gray-500">Loading workflow runs...</div>
          </div>
        ) : runsError ? (
          <div className="p-6 text-center">
            <div className="text-red-500">Error loading workflow runs</div>
            <Button onClick={handleRefresh} className="mt-2">
              Retry
            </Button>
          </div>
        ) : workflowRuns.length === 0 ? (
          <div className="p-6 text-center">
            <div className="text-gray-500">No workflow runs found</div>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  {table.getHeaderGroups().map((headerGroup) => (
                    <TableRow key={headerGroup.id}>
                      {headerGroup.headers.map((header) => (
                        <TableHead key={header.id}>
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                        </TableHead>
                      ))}
                    </TableRow>
                  ))}
                </TableHeader>
                <TableBody>
                  {table.getRowModel().rows?.length ? (
                    table.getRowModel().rows.map((row) => (
                      <TableRow
                        key={row.id}
                        data-state={row.getIsSelected() && 'selected'}
                        className="cursor-pointer"
                        onClick={() => handleRowClick(row.original)}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={columns.length} className="h-24 text-center">
                        No results.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            <div className="flex items-center justify-between border-t border-gray-200 px-6 py-4">
              <div className="text-sm text-gray-500">
                Showing {pageIndex * PAGE_SIZE + 1} to {Math.min((pageIndex + 1) * PAGE_SIZE, totalCount)} of{' '}
                {totalCount} results
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => table.previousPage()}
                  disabled={!table.getCanPreviousPage()}
                >
                  Previous
                </Button>
                <Button variant="outline" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </div>

      <Dialog open={isInferencePopupOpen} onOpenChange={setIsInferencePopupOpen}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Publish to Pipeline</DialogTitle>
          </DialogHeader>
          <InferencePopup
            renderModal={false}
            onClose={(newRunId?: string) => {
              setIsInferencePopupOpen(false);
              handleRefresh();
              // If a new run was created, add it to active runs for polling
              if (newRunId) {
                addActiveRun(newRunId);
              }
            }}
          />
        </DialogContent>
      </Dialog>

      {/* Output Dialog */}
      <Dialog open={isOutputPopupOpen} onOpenChange={setIsOutputPopupOpen}>
        <DialogContent className="max-h-[80vh] max-w-4xl">
          <DialogHeader>
            <DialogTitle>Workflow Run Output</DialogTitle>
            <DialogDescription>View the output of the selected workflow run</DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-auto">
            {selectedRunOutput ? (
              <pre className="text-sm wrap-break-word whitespace-pre-wrap text-gray-900">
                {formatOutput(selectedRunOutput)}
              </pre>
            ) : (
              <div className="text-center text-gray-500">No output available</div>
            )}
          </div>
          <DialogFooter>
            <Button onClick={() => setIsOutputPopupOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default WorkflowPipelineDetail;
