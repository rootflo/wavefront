import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Textarea } from '@app/components/ui/textarea';
import { useNotifyStore } from '@app/store';
import { ScheduledJob } from '@app/types/scheduled-job';
import floConsoleService from '@app/api';
import { useEffect, useMemo, useState } from 'react';

interface ScheduleEmailAlertDialogProps {
  isOpen: boolean;
  datasourceId: string;
  queryId: string;
  onOpenChange: (open: boolean) => void;
}

const ScheduleEmailAlertDialog: React.FC<ScheduleEmailAlertDialogProps> = ({
  isOpen,
  datasourceId,
  queryId,
  onOpenChange,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [recipientsText, setRecipientsText] = useState('');
  const [subject, setSubject] = useState('');
  const [queryParamsJson, setQueryParamsJson] = useState('');
  const [dateRange, setDateRange] = useState<'none' | 'last_day' | 'last_7_days' | 'last_30_days'>('none');
  const [startDateParamKey, setStartDateParamKey] = useState('start_date');
  const [endDateParamKey, setEndDateParamKey] = useState('end_date');
  const [maxRetries, setMaxRetries] = useState('3');
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const recipients = useMemo(
    () =>
      recipientsText
        .split(',')
        .map((email) => email.trim())
        .filter(Boolean),
    [recipientsText]
  );

  const resetForm = () => {
    setCronExpr('0 9 * * *');
    setTimezone('Asia/Kolkata');
    setRecipientsText('');
    setSubject('');
    setQueryParamsJson('');
    setDateRange('none');
    setStartDateParamKey('start_date');
    setEndDateParamKey('end_date');
    setMaxRetries('3');
    setEditingJobId(null);
    setError('');
  };

  const fetchJobs = async () => {
    if (!datasourceId || !queryId) return;
    setLoadingJobs(true);
    try {
      const response = await floConsoleService.scheduledJobService.listScheduledJobs({
        limit: 100,
        query_id: queryId,
        datasource_id: datasourceId,
      });
      setJobs(response.data.data?.jobs || []);
    } catch {
      notifyError('Failed to fetch existing schedules');
    } finally {
      setLoadingJobs(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void fetchJobs();
    } else {
      setJobs([]);
      resetForm();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, datasourceId, queryId]);

  const handleOpenChange = (open: boolean) => {
    if (!open && !saving) {
      resetForm();
    }
    onOpenChange(open);
  };

  const handleSave = async () => {
    const retries = Number(maxRetries);
    if (!cronExpr.trim()) {
      setError('Cron expression is required');
      return;
    }
    if (!timezone.trim()) {
      setError('Timezone is required');
      return;
    }
    if (recipients.length === 0) {
      setError('At least one recipient email is required');
      return;
    }
    if (!Number.isInteger(retries) || retries < 0 || retries > 10) {
      setError('Max retries must be an integer between 0 and 10');
      return;
    }
    let parsedParams: Record<string, unknown> | undefined;
    if (queryParamsJson.trim()) {
      try {
        const value = JSON.parse(queryParamsJson);
        if (typeof value !== 'object' || value === null || Array.isArray(value)) {
          setError('Query params must be a JSON object');
          return;
        }
        parsedParams = value as Record<string, unknown>;
      } catch {
        setError('Query params must be valid JSON (object)');
        return;
      }
    }

    setSaving(true);
    setError('');
    try {
      if (editingJobId) {
        await floConsoleService.scheduledJobService.updateScheduledJob(editingJobId, {
          cron_expr: cronExpr.trim(),
          timezone: timezone.trim(),
          max_retries: retries,
          payload: {
            datasource_id: datasourceId,
            query_id: queryId,
            recipients,
            subject: subject.trim() || undefined,
            date_range: dateRange === 'none' ? undefined : dateRange,
            start_date_param: dateRange === 'none' ? undefined : startDateParamKey.trim() || 'start_date',
            end_date_param: dateRange === 'none' ? undefined : endDateParamKey.trim() || 'end_date',
            params: parsedParams,
          },
        });
        notifySuccess('Schedule updated successfully');
      } else {
        await floConsoleService.scheduledJobService.createScheduledJob({
          job_type: 'email_dynamic_query',
          cron_expr: cronExpr.trim(),
          timezone: timezone.trim(),
          max_retries: retries,
          payload: {
            datasource_id: datasourceId,
            query_id: queryId,
            recipients,
            subject: subject.trim() || undefined,
            date_range: dateRange === 'none' ? undefined : dateRange,
            start_date_param: dateRange === 'none' ? undefined : startDateParamKey.trim() || 'start_date',
            end_date_param: dateRange === 'none' ? undefined : endDateParamKey.trim() || 'end_date',
            params: parsedParams,
          },
        });
        notifySuccess('Email alert scheduled successfully');
      }
      resetForm();
      await fetchJobs();
    } catch {
      setError('Unable to create schedule. Please verify the details and try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (job: ScheduledJob) => {
    setEditingJobId(job.id);
    setCronExpr(job.cron_expr || '0 9 * * *');
    setTimezone(job.timezone || 'Asia/Kolkata');
    setMaxRetries(String(job.max_retries ?? 3));
    const payload = (job.payload || {}) as Record<string, unknown>;
    const recipients = Array.isArray(payload.recipients) ? payload.recipients : [];
    setRecipientsText(recipients.map((item) => String(item)).join(', '));
    setSubject(typeof payload.subject === 'string' ? payload.subject : '');
    const paramsValue = payload.params;
    const dateRangeValue = payload.date_range;
    if (dateRangeValue === 'last_day' || dateRangeValue === 'last_7_days' || dateRangeValue === 'last_30_days') {
      setDateRange(dateRangeValue);
    } else {
      setDateRange('none');
    }
    setStartDateParamKey(typeof payload.start_date_param === 'string' ? payload.start_date_param : 'start_date');
    setEndDateParamKey(typeof payload.end_date_param === 'string' ? payload.end_date_param : 'end_date');
    if (paramsValue && typeof paramsValue === 'object' && !Array.isArray(paramsValue)) {
      setQueryParamsJson(JSON.stringify(paramsValue, null, 2));
    } else {
      setQueryParamsJson('');
    }
  };

  const handleDelete = async (jobId: string) => {
    setSaving(true);
    try {
      await floConsoleService.scheduledJobService.deleteScheduledJob(jobId);
      notifySuccess('Schedule deleted successfully');
      if (editingJobId === jobId) {
        resetForm();
      }
      await fetchJobs();
    } catch {
      notifyError('Failed to delete schedule');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[800px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Schedule Email Alert</DialogTitle>
          <DialogDescription>Create a scheduled query email for this dynamic query.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-5">
          <div className="rounded-lg border border-[#EFF0F1] bg-[#FBFBFB] p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold text-[#282828]">Existing schedules for this query</p>
              <Button
                variant="outline"
                onClick={() => {
                  resetForm();
                }}
                disabled={saving}
              >
                New Schedule
              </Button>
            </div>
            {loadingJobs ? (
              <p className="text-sm text-[#878787]">Loading schedules...</p>
            ) : jobs.length === 0 ? (
              <p className="text-sm text-[#878787]">No schedules found for this dynamic query.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {jobs.map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between rounded-md border border-[#EFF0F1] bg-white p-3"
                  >
                    <div className="text-xs text-[#282828]">
                      <p>
                        <span className="font-medium">Cron:</span> {job.cron_expr} ({job.timezone})
                      </p>
                      <p>
                        <span className="font-medium">Status:</span> {job.status}
                      </p>
                      <p>
                        <span className="font-medium">Next Run:</span>{' '}
                        {job.next_run_at ? new Date(job.next_run_at).toLocaleString() : '-'}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={() => handleEdit(job)} disabled={saving}>
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={() => {
                          void handleDelete(job.id);
                        }}
                        disabled={saving}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Datasource ID</p>
              <Input value={datasourceId} disabled />
            </div>
            <div>
              <p className="mb-1 text-xs text-[#878787]">Query ID</p>
              <Input value={queryId} disabled />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Cron expression</p>
              <Input value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder="0 9 * * *" />
            </div>
            <div>
              <p className="mb-1 text-xs text-[#878787]">Timezone</p>
              <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="Asia/Kolkata" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Max retries</p>
              <Input value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} placeholder="3" />
            </div>
            <div>
              <p className="mb-1 text-xs text-[#878787]">Subject (optional)</p>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Daily report" />
            </div>
          </div>

          <div>
            <p className="mb-1 text-xs text-[#878787]">Recipients (comma-separated emails)</p>
            <Textarea
              value={recipientsText}
              onChange={(e) => setRecipientsText(e.target.value)}
              placeholder="user1@company.com, user2@company.com"
              className="min-h-[90px]"
            />
          </div>

          <div>
            <p className="mb-1 text-xs text-[#878787]">Query params (optional JSON)</p>
            <Textarea
              value={queryParamsJson}
              onChange={(e) => setQueryParamsJson(e.target.value)}
              placeholder={'{"start_date":"2026-03-01","end_date":"2026-03-31"}'}
              className="min-h-[90px] font-mono"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Dynamic date range (optional)</p>
              <Select value={dateRange} onValueChange={(v) => setDateRange(v as typeof dateRange)}>
                <SelectTrigger>
                  <SelectValue placeholder="Select range" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="last_day">Last day</SelectItem>
                  <SelectItem value="last_7_days">Last 7 days</SelectItem>
                  <SelectItem value="last_30_days">Last 30 days</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <p className="mb-1 text-xs text-[#878787]">Start date param key</p>
              <Input value={startDateParamKey} onChange={(e) => setStartDateParamKey(e.target.value)} />
            </div>
            <div>
              <p className="mb-1 text-xs text-[#878787]">End date param key</p>
              <Input value={endDateParamKey} onChange={(e) => setEndDateParamKey(e.target.value)} />
            </div>
          </div>

          {error ? <p className="text-sm text-red-500">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} loading={saving} disabled={saving}>
            {editingJobId ? 'Update Schedule' : 'Create Schedule'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ScheduleEmailAlertDialog;
