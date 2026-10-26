import ListHeader, { FilterSelect } from '@app/components/ListHeader';
import { toneClass } from '@app/lib/tones';
import { ResourceListSkeleton } from '@app/components/ResourceList';
import ResourceCard from '@app/components/ResourceCard';
import { CalendarClock, Play, Pause } from 'lucide-react';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import {
  useDeleteScheduledJob,
  useGetAllDatasources,
  useGetAppUsers,
  useGetScheduledJobs,
  useSetScheduledJobPaused,
} from '@app/hooks';
import { cn } from '@app/lib/utils';
import { useDashboardStore } from '@app/store';
import { ScheduledJob } from '@app/types/scheduled-job';
import { useMemo, useState } from 'react';
import { useParams } from 'react-router';
import ScheduledJobFormDialog from './ScheduledJobFormDialog';
import {
  extractRecipientUserIdsFromPayload,
  formatDateTime,
  formatJobQueriesLabel,
  getDatasourceIdFromPayload,
  resolveUsersFromRecipientIds,
} from './scheduled-job-utils';
import PageBreadcrumb from '@app/components/PageBreadcrumb';
import { useDeleteConfirm } from '@app/hooks';
import { matchesSearch } from '@app/utils/search';

const statusBadgeClass: Record<string, string> = {
  active: toneClass.success,
  paused: toneClass.warning,
  running: toneClass.info,
  failed: toneClass.danger,
  completed: toneClass.neutral,
};

const ScheduledJobsPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const setJobPaused = useSetScheduledJobPaused(appId);
  const deleteScheduledJob = useDeleteScheduledJob(appId);
  const deletion = useDeleteConfirm<ScheduledJob>((item) => deleteScheduledJob.mutateAsync(item.id));
  const { selectedApp } = useDashboardStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [formOpen, setFormOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null);

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
      return matchesSearch(
        term,
        job.cron_expr,
        job.timezone,
        job.status,
        datasourceName,
        datasourceId,
        formatJobQueriesLabel(job),
        String(payload.subject || '')
      );
    });
  }, [jobs, searchTerm, statusFilter, datasourceNameById]);

  const handleCreate = () => {
    setEditingJob(null);
    setFormOpen(true);
  };

  const handleEdit = (job: ScheduledJob) => {
    setEditingJob(job);
    setFormOpen(true);
  };

  const handlePauseResume = (job: ScheduledJob) => {
    const resuming = job.status === 'paused' || job.status === 'failed';
    setJobPaused.mutate({ jobId: job.id, paused: !resuming, wasFailed: job.status === 'failed' });
  };

  /** Disables just the row whose pause/resume is in flight. */
  const isActing = (jobId: string) => setJobPaused.isPending && setJobPaused.variables?.jobId === jobId;

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
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden p-4 max-md:overflow-y-auto sm:p-8">
      <PageBreadcrumb items={[{ label: 'Scheduled Jobs', to: `/apps/${appId}/scheduled-jobs` }]} />

      <ListHeader
        title="Scheduled Jobs"
        count={filteredJobs.length || undefined}
        subtitle={<>Manage email report schedules for {selectedApp?.app_name}</>}
        search={{ value: searchTerm, onChange: setSearchTerm, placeholder: 'Search scheduled jobs' }}
        filters={
          <FilterSelect
            label="Status"
            value={statusFilter}
            onValueChange={setStatusFilter}
            allValue="all"
            options={[
              { value: 'all', label: 'All' },
              { value: 'active', label: 'Active' },
              { value: 'paused', label: 'Paused' },
              { value: 'running', label: 'Running' },
              { value: 'failed', label: 'Failed' },
              { value: 'completed', label: 'Completed' },
            ]}
          />
        }
        primary={{ label: 'Create schedule', onClick: handleCreate }}
      />

      {isLoading ? (
        <ResourceListSkeleton view="table" />
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
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1 max-md:flex-none">
          <div data-mobile-cards className="flex flex-col gap-3 pb-24 md:hidden">
            {filteredJobs.map((job) => {
              const datasourceId = getDatasourceIdFromPayload(job.payload || {});
              const canPauseResume = job.status === 'active' || job.status === 'paused' || job.status === 'failed';
              const resume = job.status === 'paused' || job.status === 'failed';
              return (
                <ResourceCard
                  key={job.id}
                  icon={CalendarClock}
                  title={datasourceNameById.get(datasourceId) || datasourceId || 'Scheduled job'}
                  description={
                    job.last_error || (formatJobQueriesLabel(job) !== '—' ? formatJobQueriesLabel(job) : undefined)
                  }
                  metadata={[
                    {
                      label: 'Status',
                      value: job.status,
                      className: cn('capitalize', statusBadgeClass[job.status] || ''),
                    },
                    { label: 'Cron', value: job.cron_expr, isMono: true },
                    { label: 'Recipients', value: getRecipientSummary(job) },
                    { label: 'Next run', value: formatDateTime(job.next_run_at) },
                    ...(job.last_run_at ? [{ label: 'Last run', value: formatDateTime(job.last_run_at) }] : []),
                  ]}
                  onEditClick={() => handleEdit(job)}
                  onDeleteClick={() => deletion.ask(job)}
                  deleteTitle="Delete schedule"
                  extraActions={
                    canPauseResume
                      ? [
                          {
                            label: resume ? 'Resume' : 'Pause',
                            icon: resume ? Play : Pause,
                            disabled: isActing(job.id),
                            onClick: () => void handlePauseResume(job),
                          },
                        ]
                      : []
                  }
                />
              );
            })}
          </div>
          <div className="max-md:hidden">
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
                  const canPauseResume = job.status === 'active' || job.status === 'paused' || job.status === 'failed';
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
                        <span className="frost-text-muted mt-0.5 block">{job.timezone}</span>
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
                              disabled={isActing(job.id)}
                              onClick={() => void handlePauseResume(job)}
                            >
                              {job.status === 'paused' || job.status === 'failed' ? 'Resume' : 'Pause'}
                            </Button>
                          ) : null}
                          <Button variant="outline" size="sm" onClick={() => handleEdit(job)}>
                            Edit
                          </Button>
                          <Button variant="destructive" size="sm" onClick={() => deletion.ask(job)}>
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
        />
      ) : null}

      {deletion.item ? (
        <DeleteConfirmationDialog
          {...deletion.dialogProps}
          title="Delete scheduled job"
          message="Are you sure you want to delete this schedule? This action cannot be undone."
          confirmLabel="Delete"
          cancelLabel="Cancel"
        />
      ) : null}
    </div>
  );
};

export default ScheduledJobsPage;
