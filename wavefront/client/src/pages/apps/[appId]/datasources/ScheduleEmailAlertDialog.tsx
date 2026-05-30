import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Badge } from '@app/components/ui/badge';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import { Input } from '@app/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { Textarea } from '@app/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@app/components/ui/tooltip';
import { useGetAppUsers } from '@app/hooks';
import { cn } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { IUser } from '@app/types/user';
import { ScheduledJob, ColumnStyleConfig } from '@app/types/scheduled-job';
import floConsoleService from '@app/api';
import { Check, ChevronDown, Info, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

interface ScheduleEmailAlertDialogProps {
  isOpen: boolean;
  appId: string;
  datasourceId: string;
  queryId: string;
  onOpenChange: (open: boolean) => void;
}

const normalizeUserId = (id: string) => id.trim().toLowerCase();

const formatUserLabel = (user: IUser) => `${user.first_name} ${user.last_name} (${user.email})`;

const extractRecipientUserIdsFromPayload = (payload: Record<string, unknown>): string[] => {
  const rawIds = payload.recipient_user_ids;
  const ids: string[] = [];
  if (Array.isArray(rawIds)) {
    for (const item of rawIds) {
      const id = String(item).trim();
      if (id) ids.push(id);
    }
  } else if (typeof rawIds === 'string' && rawIds.trim()) {
    ids.push(rawIds.trim());
  }
  return ids;
};

const resolveUsersFromRecipientIds = (ids: string[], users: IUser[]): IUser[] => {
  const resolved: IUser[] = [];
  const seen = new Set<string>();
  for (const id of ids) {
    const user = users.find((u) => normalizeUserId(u.id) === normalizeUserId(id));
    if (user && !seen.has(normalizeUserId(user.id))) {
      seen.add(normalizeUserId(user.id));
      resolved.push(user);
    }
  }
  return resolved;
};

const COLUMN_STYLES_PLACEHOLDER = `[
  {
    "column": "Total calls attempted",
    "rules": [
      { "op": "eq", "value": 0, "fill": "light_red" },
      { "op": "lt", "value": 160, "fill": "light_yellow" },
      { "op": "lt", "value": 225, "fill": "light_green" },
      { "op": "gte", "value": 225, "fill": "dark_green" }
    ]
  }
]`;

const ScheduleEmailAlertDialog: React.FC<ScheduleEmailAlertDialogProps> = ({
  isOpen,
  appId,
  datasourceId,
  queryId,
  onOpenChange,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [selectedRecipientUserIds, setSelectedRecipientUserIds] = useState<string[]>([]);
  const [recipientsSelectOpen, setRecipientsSelectOpen] = useState(false);
  const { data: appUsers = [], isLoading: appUsersLoading } = useGetAppUsers(appId);

  const selectedRecipientUsers = useMemo(
    () => resolveUsersFromRecipientIds(selectedRecipientUserIds, appUsers),
    [selectedRecipientUserIds, appUsers]
  );

  const isRecipientSelected = (userId: string) =>
    selectedRecipientUserIds.some((id) => normalizeUserId(id) === normalizeUserId(userId));

  const toggleRecipientUser = (userId: string) => {
    setSelectedRecipientUserIds((prev) =>
      isRecipientSelected(userId)
        ? prev.filter((id) => normalizeUserId(id) !== normalizeUserId(userId))
        : [...prev, userId]
    );
  };

  const removeRecipientUser = (userId: string) => {
    setSelectedRecipientUserIds((prev) => prev.filter((id) => normalizeUserId(id) !== normalizeUserId(userId)));
  };

  const applyJobToForm = (job: ScheduledJob) => {
    setEditingJobId(job.id);
    setCronExpr(job.cron_expr || '0 9 * * *');
    setTimezone(job.timezone || 'Asia/Kolkata');
    setMaxRetries(String(job.max_retries ?? 3));
    const payload = (job.payload || {}) as Record<string, unknown>;
    setSelectedRecipientUserIds(extractRecipientUserIdsFromPayload(payload));
    setSubject(typeof payload.subject === 'string' ? payload.subject : '');
    setEmailContent(typeof payload.email_content === 'string' ? payload.email_content : '');
    const paramsValue = payload.params;
    const dateRangeValue = payload.date_range;
    if (
      dateRangeValue === 'last_day' ||
      dateRangeValue === 'last_hour' ||
      dateRangeValue === 'last_7_days' ||
      dateRangeValue === 'last_30_days'
    ) {
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
    const columnStylesValue = payload.column_styles;
    if (Array.isArray(columnStylesValue) && columnStylesValue.length > 0) {
      setColumnStylesJson(JSON.stringify(columnStylesValue, null, 2));
    } else {
      setColumnStylesJson('');
    }
    setError('');
  };

  const getJobRecipientLabels = (job: ScheduledJob): string[] => {
    const payload = (job.payload || {}) as Record<string, unknown>;
    return resolveUsersFromRecipientIds(extractRecipientUserIdsFromPayload(payload), appUsers).map(formatUserLabel);
  };
  const [subject, setSubject] = useState('');
  const [emailContent, setEmailContent] = useState('');
  const [queryParamsJson, setQueryParamsJson] = useState('');
  const [columnStylesJson, setColumnStylesJson] = useState('');
  const [dateRange, setDateRange] = useState<'none' | 'last_day' | 'last_hour' | 'last_7_days' | 'last_30_days'>(
    'none'
  );
  const [startDateParamKey, setStartDateParamKey] = useState('start_date');
  const [endDateParamKey, setEndDateParamKey] = useState('end_date');
  const [maxRetries, setMaxRetries] = useState('3');
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'schedule' | 'email'>('schedule');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const resetForm = () => {
    setCronExpr('0 9 * * *');
    setTimezone('Asia/Kolkata');
    setSelectedRecipientUserIds([]);
    setSubject('');
    setEmailContent('');
    setQueryParamsJson('');
    setColumnStylesJson('');
    setDateRange('none');
    setStartDateParamKey('start_date');
    setEndDateParamKey('end_date');
    setMaxRetries('3');
    setEditingJobId(null);
    setActiveTab('schedule');
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
      setActiveTab('schedule');
      return;
    }
    if (!timezone.trim()) {
      setError('Timezone is required');
      setActiveTab('schedule');
      return;
    }
    if (selectedRecipientUserIds.length === 0) {
      setError('At least one recipient user is required');
      setActiveTab('email');
      return;
    }
    if (!Number.isInteger(retries) || retries < 0 || retries > 10) {
      setError('Max retries must be an integer between 0 and 10');
      setActiveTab('schedule');
      return;
    }
    let parsedParams: Record<string, unknown> | undefined;
    if (queryParamsJson.trim()) {
      try {
        const value = JSON.parse(queryParamsJson);
        if (typeof value !== 'object' || value === null || Array.isArray(value)) {
          setError('Query params must be a JSON object');
          setActiveTab('schedule');
          return;
        }
        parsedParams = value as Record<string, unknown>;
      } catch {
        setError('Query params must be valid JSON (object)');
        setActiveTab('schedule');
        return;
      }
    }

    let parsedColumnStyles: ColumnStyleConfig[] | undefined;
    if (columnStylesJson.trim()) {
      try {
        const value = JSON.parse(columnStylesJson);
        if (!Array.isArray(value)) {
          setError('Column styles must be a JSON array');
          setActiveTab('email');
          return;
        }
        parsedColumnStyles = value as ColumnStyleConfig[];
      } catch {
        setError('Column styles must be valid JSON (array)');
        setActiveTab('email');
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
            recipient_user_ids: selectedRecipientUserIds,
            subject: subject.trim() || undefined,
            email_content: emailContent.trim() || undefined,
            column_styles: parsedColumnStyles,
            date_range: dateRange === 'none' ? undefined : dateRange,
            start_date_param: dateRange === 'none' ? undefined : startDateParamKey.trim() || 'start_date',
            end_date_param: dateRange === 'none' ? undefined : endDateParamKey.trim() || 'end_date',
            params: parsedParams,
          },
        });
        notifySuccess('Schedule updated successfully');
        await fetchJobs();
      } else {
        await floConsoleService.scheduledJobService.createScheduledJob({
          job_type: 'email_dynamic_query',
          cron_expr: cronExpr.trim(),
          timezone: timezone.trim(),
          max_retries: retries,
          payload: {
            datasource_id: datasourceId,
            query_id: queryId,
            recipient_user_ids: selectedRecipientUserIds,
            subject: subject.trim() || undefined,
            email_content: emailContent.trim() || undefined,
            column_styles: parsedColumnStyles,
            date_range: dateRange === 'none' ? undefined : dateRange,
            start_date_param: dateRange === 'none' ? undefined : startDateParamKey.trim() || 'start_date',
            end_date_param: dateRange === 'none' ? undefined : endDateParamKey.trim() || 'end_date',
            params: parsedParams,
          },
        });
        notifySuccess('Email alert scheduled successfully');
        resetForm();
        await fetchJobs();
      }
    } catch {
      setError('Unable to create schedule. Please verify the details and try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (job: ScheduledJob) => {
    applyJobToForm(job);
    setActiveTab('email');
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
      <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-[800px] xl:max-w-[1000px]">
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
                    className={cn(
                      'flex items-center justify-between rounded-md border bg-white p-3',
                      editingJobId === job.id ? 'border-[#282828]' : 'border-[#EFF0F1]'
                    )}
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
                      <p>
                        <span className="font-medium">Recipients:</span>{' '}
                        {appUsersLoading
                          ? 'Loading...'
                          : (() => {
                              const labels = getJobRecipientLabels(job);
                              return labels.length > 0 ? labels.join(', ') : 'None';
                            })()}
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

          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'schedule' | 'email')}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="schedule">Schedule</TabsTrigger>
              <TabsTrigger value="email">Email</TabsTrigger>
            </TabsList>

            <TabsContent value="schedule" className="mt-4 space-y-5">
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

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <p className="mb-1 text-xs text-[#878787]">Cron expression</p>
                  <Input value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder="0 9 * * *" />
                </div>
                <div>
                  <p className="mb-1 text-xs text-[#878787]">Timezone</p>
                  <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="Asia/Kolkata" />
                </div>
                <div>
                  <p className="mb-1 text-xs text-[#878787]">Max retries</p>
                  <Input value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} placeholder="3" />
                </div>
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
                      <SelectItem value="last_hour">Last hour</SelectItem>
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

              <div>
                <p className="mb-1 text-xs text-[#878787]">Query params (optional JSON)</p>
                <Textarea
                  value={queryParamsJson}
                  onChange={(e) => setQueryParamsJson(e.target.value)}
                  placeholder={'{"start_date":"2026-03-01","end_date":"2026-03-31"}'}
                  className="min-h-[90px] font-mono"
                />
              </div>
            </TabsContent>

            <TabsContent value="email" className="mt-4 space-y-5">
              <TooltipProvider delayDuration={200}>
                <div>
                  <p className="mb-1 text-xs text-[#878787]">Subject (optional)</p>
                  <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Daily report" />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="mb-1 flex items-center gap-1.5">
                      <p className="text-xs text-[#878787]">Email content (optional)</p>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            className="inline-flex cursor-pointer text-[#878787] hover:text-[#555555]"
                            aria-label="Email content help"
                          >
                            <Info className="h-3.5 w-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs">
                          HTML is supported. Leave empty to use the default report summary.
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <Textarea
                      value={emailContent}
                      onChange={(e) => setEmailContent(e.target.value)}
                      placeholder="<p>Your daily report is ready.</p>"
                      className="min-h-[120px]"
                    />
                  </div>

                  <div>
                    <div className="mb-1 flex items-center gap-1.5">
                      <p className="text-xs text-[#878787]">Column styles (optional JSON)</p>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            className="inline-flex cursor-pointer text-[#878787] hover:text-[#555555]"
                            aria-label="Column styles help"
                          >
                            <Info className="h-3.5 w-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs">
                          Rules are evaluated top-to-bottom; first match wins. Fills: light_red, light_yellow,
                          light_green, dark_green, or a hex color.
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <Textarea
                      value={columnStylesJson}
                      onChange={(e) => setColumnStylesJson(e.target.value)}
                      placeholder={COLUMN_STYLES_PLACEHOLDER}
                      className="min-h-[120px] font-mono text-xs"
                    />
                  </div>
                </div>

                <div>
                  <div className="mb-1 flex items-center gap-1.5">
                    <p className="text-xs text-[#878787]">Recipient users</p>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          className="inline-flex cursor-pointer text-[#878787] hover:text-[#555555]"
                          aria-label="Recipient users help"
                        >
                          <Info className="h-3.5 w-3.5" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        Each user receives a report filtered by their data access (RLS).
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <Popover modal open={recipientsSelectOpen} onOpenChange={setRecipientsSelectOpen}>
                    <PopoverTrigger asChild>
                      <button
                        type="button"
                        role="combobox"
                        aria-expanded={recipientsSelectOpen}
                        disabled={appUsersLoading}
                        className={cn(
                          'border-input ring-offset-background focus:ring-ring flex min-h-9 w-full items-center justify-between rounded-md border bg-white px-3 py-2 text-sm shadow-sm focus:ring-1 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
                          selectedRecipientUserIds.length === 0 && 'text-[#878787]'
                        )}
                      >
                        <span className="truncate text-left">
                          {appUsersLoading
                            ? 'Loading users...'
                            : selectedRecipientUserIds.length === 0
                              ? 'Select recipient users'
                              : selectedRecipientUsers.length === 0
                                ? `${selectedRecipientUserIds.length} user${selectedRecipientUserIds.length === 1 ? '' : 's'} selected`
                                : selectedRecipientUsers.length <= 2
                                  ? selectedRecipientUsers.map((u) => formatUserLabel(u)).join(', ')
                                  : `${selectedRecipientUsers.length} users selected`}
                        </span>
                        <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
                      <Command>
                        <CommandInput placeholder="Search users..." />
                        <CommandList
                          onWheel={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            e.currentTarget.scrollTop += e.deltaY;
                          }}
                        >
                          <CommandEmpty>No users found.</CommandEmpty>
                          {selectedRecipientUsers.length > 0 ? (
                            <CommandGroup heading="Selected">
                              {selectedRecipientUsers.map((user) => (
                                <CommandItem
                                  key={`selected-${user.id}`}
                                  value={`selected-${user.id}-${user.email}`}
                                  onSelect={() => toggleRecipientUser(user.id)}
                                >
                                  <Check className="mr-2 h-4 w-4 shrink-0 opacity-100" />
                                  {formatUserLabel(user)}
                                </CommandItem>
                              ))}
                            </CommandGroup>
                          ) : null}
                          <CommandGroup heading="All users">
                            {appUsers
                              .filter((user) => !isRecipientSelected(user.id))
                              .map((user) => (
                                <CommandItem
                                  key={user.id}
                                  value={`${user.first_name} ${user.last_name} ${user.email}`}
                                  onSelect={() => toggleRecipientUser(user.id)}
                                >
                                  <Check className="mr-2 h-4 w-4 shrink-0 opacity-0" />
                                  {formatUserLabel(user)}
                                </CommandItem>
                              ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                  {selectedRecipientUsers.length > 0 ? (
                    <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                      {selectedRecipientUsers.map((user) => (
                        <Badge key={user.id} variant="secondary" className="shrink-0 gap-1 pr-1 font-normal">
                          <span className="max-w-[240px] truncate">{formatUserLabel(user)}</span>
                          <button
                            type="button"
                            className="rounded-full p-0.5 hover:bg-black/10"
                            aria-label={`Remove ${formatUserLabel(user)}`}
                            onClick={() => removeRecipientUser(user.id)}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
              </TooltipProvider>
            </TabsContent>
          </Tabs>

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
