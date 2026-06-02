import floConsoleService from '@app/api';
import { Badge } from '@app/components/ui/badge';
import { Button } from '@app/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Input } from '@app/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { Textarea } from '@app/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@app/components/ui/tooltip';
import { useGetAllDatasources, useGetAllYamls, useGetAppUsers } from '@app/hooks';
import { cn } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { ColumnStyleConfig, ScheduledJob } from '@app/types/scheduled-job';
import { Check, ChevronDown, Info, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  buildEmailPayload,
  extractRecipientUserIdsFromPayload,
  formatUserLabel,
  getDatasourceIdFromPayload,
  getQueryIdsFromPayload,
  normalizeUserId,
  resolveUsersFromRecipientIds,
} from './scheduled-job-utils';

const COLUMN_STYLES_PLACEHOLDER = `[
  {
    "column": "Total calls attempted",
    "rules": [
      { "op": "eq", "value": 0, "fill": "light_red" },
      { "op": "lt", "value": 160, "fill": "light_yellow" },
      { "op": "gte", "value": 225, "fill": "dark_green" }
    ]
  }
]`;

interface ScheduledJobFormDialogProps {
  isOpen: boolean;
  appId: string;
  job?: ScheduledJob | null;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

const ScheduledJobFormDialog: React.FC<ScheduledJobFormDialogProps> = ({
  isOpen,
  appId,
  job,
  onOpenChange,
  onSuccess,
}) => {
  const { notifySuccess } = useNotifyStore();
  const isEditing = Boolean(job?.id);
  const { data: datasources = [] } = useGetAllDatasources(appId);
  const { data: appUsers = [], isLoading: appUsersLoading } = useGetAppUsers(appId);

  const [datasourceId, setDatasourceId] = useState('');
  const [selectedQueryIds, setSelectedQueryIds] = useState<string[]>([]);
  const { data: yamls = [], isLoading: yamlsLoading } = useGetAllYamls(appId, datasourceId || undefined);

  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [selectedRecipientUserIds, setSelectedRecipientUserIds] = useState<string[]>([]);
  const [recipientsSelectOpen, setRecipientsSelectOpen] = useState(false);
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
  const [activeTab, setActiveTab] = useState<'schedule' | 'email'>('schedule');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const availableQueryIds = useMemo(
    () => yamls.map((yaml) => yaml.file.split('.')[0]).filter((id) => id.length > 0),
    [yamls]
  );

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

  const toggleQueryId = (queryId: string) => {
    setSelectedQueryIds((prev) => (prev.includes(queryId) ? prev.filter((id) => id !== queryId) : [...prev, queryId]));
  };

  const resetForm = () => {
    setDatasourceId('');
    setSelectedQueryIds([]);
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
    setActiveTab('schedule');
    setError('');
  };

  const applyJobToForm = (existingJob: ScheduledJob) => {
    const payload = (existingJob.payload || {}) as Record<string, unknown>;
    setDatasourceId(getDatasourceIdFromPayload(payload));
    setSelectedQueryIds(getQueryIdsFromPayload(payload));
    setCronExpr(existingJob.cron_expr || '0 9 * * *');
    setTimezone(existingJob.timezone || 'Asia/Kolkata');
    setMaxRetries(String(existingJob.max_retries ?? 3));
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

  useEffect(() => {
    if (!isOpen) {
      resetForm();
      return;
    }
    if (job) {
      applyJobToForm(job);
    } else {
      resetForm();
    }
  }, [isOpen, job]);

  const handleOpenChange = (open: boolean) => {
    if (!open && !saving) {
      resetForm();
    }
    onOpenChange(open);
  };

  const handleSave = async () => {
    const retries = Number(maxRetries);
    if (!datasourceId.trim()) {
      setError('Datasource is required');
      setActiveTab('schedule');
      return;
    }
    if (selectedQueryIds.length === 0) {
      setError('Select at least one dynamic query');
      setActiveTab('schedule');
      return;
    }
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

    const emailPayload = buildEmailPayload({
      datasourceId: datasourceId.trim(),
      queryIds: selectedQueryIds,
      recipientUserIds: selectedRecipientUserIds,
      subject: subject.trim() || undefined,
      emailContent: emailContent.trim() || undefined,
      columnStyles: parsedColumnStyles,
      dateRange: dateRange === 'none' ? undefined : dateRange,
      startDateParam: dateRange === 'none' ? undefined : startDateParamKey.trim() || 'start_date',
      endDateParam: dateRange === 'none' ? undefined : endDateParamKey.trim() || 'end_date',
      params: parsedParams,
    });

    setSaving(true);
    setError('');
    try {
      if (isEditing && job) {
        await floConsoleService.scheduledJobService.updateScheduledJob(job.id, {
          cron_expr: cronExpr.trim(),
          timezone: timezone.trim(),
          max_retries: retries,
          payload: emailPayload,
        });
        notifySuccess('Scheduled job updated successfully');
      } else {
        await floConsoleService.scheduledJobService.createScheduledJob({
          job_type: 'email_dynamic_query',
          cron_expr: cronExpr.trim(),
          timezone: timezone.trim(),
          max_retries: retries,
          payload: emailPayload,
        });
        notifySuccess('Scheduled job created successfully');
      }
      onSuccess();
      handleOpenChange(false);
    } catch {
      setError('Unable to save scheduled job. Please verify the details and try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-[800px] xl:max-w-[1000px]">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Scheduled Job' : 'Create Scheduled Job'}</DialogTitle>
          <DialogDescription>
            Schedule one or more dynamic query reports to be emailed on a cron schedule.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'schedule' | 'email')}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="schedule">Schedule</TabsTrigger>
            <TabsTrigger value="email">Email</TabsTrigger>
          </TabsList>

          <TabsContent value="schedule" className="mt-4 space-y-5">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="mb-1 text-xs text-[#878787]">Datasource</p>
                <Select
                  value={datasourceId}
                  onValueChange={(value) => {
                    setDatasourceId(value);
                    if (!job || getDatasourceIdFromPayload(job.payload || {}) !== value) {
                      setSelectedQueryIds([]);
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select datasource" />
                  </SelectTrigger>
                  <SelectContent>
                    {datasources.map((ds) => (
                      <SelectItem key={ds.id} value={ds.id}>
                        {ds.name || ds.id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <p className="mb-1 text-xs text-[#878787]">Max retries</p>
                <Input value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} placeholder="3" />
              </div>
            </div>

            <div>
              <p className="mb-2 text-xs text-[#878787]">
                Dynamic queries (select one or more — each becomes an attachment in the email)
              </p>
              {!datasourceId ? (
                <p className="text-sm text-[#878787]">Select a datasource to load queries.</p>
              ) : yamlsLoading ? (
                <p className="text-sm text-[#878787]">Loading queries...</p>
              ) : availableQueryIds.length === 0 ? (
                <p className="text-sm text-[#878787]">No dynamic queries found for this datasource.</p>
              ) : (
                <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded-md border border-[#EFF0F1] bg-[#FBFBFB] p-3">
                  {availableQueryIds.map((queryId) => {
                    const selected = selectedQueryIds.includes(queryId);
                    return (
                      <button
                        key={queryId}
                        type="button"
                        onClick={() => toggleQueryId(queryId)}
                        className={cn(
                          'rounded-full border px-3 py-1 text-xs transition-colors',
                          selected
                            ? 'border-[#282828] bg-[#282828] text-white'
                            : 'border-[#EFF0F1] bg-white text-[#282828] hover:border-[#282828]'
                        )}
                      >
                        {queryId}
                      </button>
                    );
                  })}
                </div>
              )}
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
                      <TooltipContent side="top" className="max-w-md">
                        {`Use {query_id} placeholders to embed result tables inline (e.g. {sales_summary}). Plain text or HTML. Excel files are still attached when under the size limit. Leave empty for the default summary.`}
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <Textarea
                    value={emailContent}
                    onChange={(e) => setEmailContent(e.target.value)}
                    placeholder={`Here is your result\n{my_query_id}\n\nSee more\n{another_query_id}`}
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
                        Rules are evaluated top-to-bottom; first match wins.
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
                      Each user receives reports filtered by their data access (RLS).
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
                      <CommandList>
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

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} loading={saving} disabled={saving}>
            {isEditing ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ScheduledJobFormDialog;
