import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Badge } from '@app/components/ui/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetAllDatasources, useGetAppUsers, useGetScheduledJobs } from '@app/hooks';
import { getScheduledJobsKey } from '@app/hooks/data/query-keys';
import { cn } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { ScheduledJob } from '@app/types/scheduled-job';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import ScheduledJobFormDialog from './ScheduledJobFormDialog';
import {
  extractRecipientUserIdsFromPayload,
  formatDateTime,
  formatJobQueriesLabel,
  getDatasourceIdFromPayload,
  resolveUsersFromRecipientIds,
} from './scheduled-job-utils';

const statusBadgeClass: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  paused: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-800',
  completed: 'bg-gray-100 text-gray-800',
};

const ScheduledJobsPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedApp } = useDashboardStore();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [formOpen, setFormOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null);
  const [deleteJob, setDeleteJob] = useState<ScheduledJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [actionJobId, setActionJobId] = useState<string | null>(null);

  const { data: jobs = [], isLoading } = useGetScheduledJobs(appId);
  const { data: datasources = [] } = useGetAllDatasources(appId);
  const { data: appUsers = [] } = useGetAppUsers(appId);

  const datasourceNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const ds of datasources) {
      map.set(ds.id, ds.name || ds.id);
    }
    return map;
  }, [datasources]);

  const filteredJobs = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return jobs.filter((job) => {
      if (statusFilter !== 'all' && job.status !== statusFilter) return false;
      if (!term) return true;
      const payload = job.payload || {};
      const datasourceId = getDatasourceIdFromPayload(payload);
      const datasourceName = datasourceNameById.get(datasourceId) || datasourceId;
      const queriesLabel = formatJobQueriesLabel(job).toLowerCase();
      const subject = String(payload.subject || '').toLowerCase();
      return (
        job.cron_expr.toLowerCase().includes(term) ||
        job.timezone.toLowerCase().includes(term) ||
        job.status.toLowerCase().includes(term) ||
        datasourceName.toLowerCase().includes(term) ||
        datasourceId.toLowerCase().includes(term) ||
        queriesLabel.includes(term) ||
        subject.includes(term)
      );
    });
  }, [jobs, searchTerm, statusFilter, datasourceNameById]);

  const refreshJobs = () => {
    queryClient.invalidateQueries({ queryKey: getScheduledJobsKey(appId || '') });
  };

  const handleCreate = () => {
    setEditingJob(null);
    setFormOpen(true);
  };

  const handleEdit = (job: ScheduledJob) => {
    setEditingJob(job);
    setFormOpen(true);
  };

  const handlePauseResume = async (job: ScheduledJob) => {
    setActionJobId(job.id);
    try {
      if (job.status === 'paused') {
        await floConsoleService.scheduledJobService.resumeScheduledJob(job.id);
        notifySuccess('Scheduled job resumed');
      } else {
        await floConsoleService.scheduledJobService.pauseScheduledJob(job.id);
        notifySuccess('Scheduled job paused');
      }
      refreshJobs();
    } catch {
      notifyError('Failed to update job status');
    } finally {
      setActionJobId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteJob) return;
    setDeleting(true);
    try {
      await floConsoleService.scheduledJobService.deleteScheduledJob(deleteJob.id);
      notifySuccess('Scheduled job deleted');
      setDeleteJob(null);
      refreshJobs();
    } catch {
      notifyError('Failed to delete scheduled job');
    } finally {
      setDeleting(false);
    }
  };

  const getRecipientSummary = (job: ScheduledJob) => {
    const ids = extractRecipientUserIdsFromPayload(job.payload || {});
    const users = resolveUsersFromRecipientIds(ids, appUsers);
    if (users.length === 0) return `${ids.length} recipient(s)`;
    if (users.length <= 2) {
      return users.map((u) => u.email).join(', ');
    }
    return `${users.length} recipients`;
  };

  return (
    <div className="flex h-full w-full flex-col p-8">
      <Breadcrumb className="mb-4">
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
                onClick={() => navigate(`/apps/${appId}/scheduled-jobs`)}
                className="hover:text-foreground cursor-pointer"
              >
                Scheduled Jobs
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-8 flex w-full items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Scheduled Jobs</h1>
          <p className="mt-2 text-gray-600">Manage email report schedules for {selectedApp?.app_name}</p>
        </div>
        <div className="flex items-center gap-3">
          <Input
            className="w-[200px]"
            type="text"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="paused">Paused</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleCreate}>Create Schedule</Button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading scheduled jobs...</p>
      ) : filteredJobs.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No scheduled jobs"
            description="Create a schedule to email dynamic query reports on a cron"
            actionText="Create Schedule"
            onActionClick={handleCreate}
          />
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#EFF0F1]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Datasource</TableHead>
                <TableHead>Queries</TableHead>
                <TableHead>Cron</TableHead>
                <TableHead>Recipients</TableHead>
                <TableHead>Next run</TableHead>
                <TableHead>Last run</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredJobs.map((job) => {
                const payload = job.payload || {};
                const datasourceId = getDatasourceIdFromPayload(payload);
                const canPauseResume = job.status === 'active' || job.status === 'paused';
                return (
                  <TableRow key={job.id}>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn('font-normal capitalize', statusBadgeClass[job.status] || '')}
                      >
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[160px] truncate" title={datasourceId}>
                      {datasourceNameById.get(datasourceId) || datasourceId || '—'}
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate" title={formatJobQueriesLabel(job)}>
                      {formatJobQueriesLabel(job)}
                    </TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      <span className="font-mono text-xs">{job.cron_expr}</span>
                      <span className="mt-0.5 block text-[#878787]">{job.timezone}</span>
                    </TableCell>
                    <TableCell className="max-w-[180px] truncate text-sm" title={getRecipientSummary(job)}>
                      {getRecipientSummary(job)}
                    </TableCell>
                    <TableCell className="text-sm whitespace-nowrap">{formatDateTime(job.next_run_at)}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">{formatDateTime(job.last_run_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        {canPauseResume ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={actionJobId === job.id}
                            onClick={() => void handlePauseResume(job)}
                          >
                            {job.status === 'paused' ? 'Resume' : 'Pause'}
                          </Button>
                        ) : null}
                        <Button variant="outline" size="sm" onClick={() => handleEdit(job)}>
                          Edit
                        </Button>
                        <Button variant="destructive" size="sm" onClick={() => setDeleteJob(job)}>
                          Delete
                        </Button>
                      </div>
                      {job.last_error ? (
                        <p className="mt-1 max-w-[240px] truncate text-xs text-red-500" title={job.last_error}>
                          {job.last_error}
                        </p>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {appId ? (
        <ScheduledJobFormDialog
          isOpen={formOpen}
          appId={appId}
          job={editingJob}
          onOpenChange={(open) => {
            setFormOpen(open);
            if (!open) setEditingJob(null);
          }}
          onSuccess={refreshJobs}
        />
      ) : null}

      {deleteJob ? (
        <DeleteConfirmationDialog
          isOpen={Boolean(deleteJob)}
          title="Delete scheduled job"
          message="Are you sure you want to delete this schedule? This action cannot be undone."
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteJob(null)}
          loading={deleting}
          confirmLabel="Delete"
          cancelLabel="Cancel"
        />
      ) : null}
    </div>
  );
};

export default ScheduledJobsPage;
