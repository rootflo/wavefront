import floConsoleService from '@app/api';
import FieldHelp from '@app/components/FieldHelp';
import MultiSelect from '@app/components/MultiSelect';
import OptionChips from '@app/components/OptionChips';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { Textarea } from '@app/components/ui/textarea';
import {
  COLUMN_STYLES_PLACEHOLDER,
  DATE_RANGE,
  DEFAULT_CRON_EXPR,
  DEFAULT_END_DATE_PARAM,
  DEFAULT_MAX_RETRIES,
  DEFAULT_START_DATE_PARAM,
  DEFAULT_TIMEZONE,
  EMAIL_CONTENT_PLACEHOLDER,
  FORM_TAB,
  JOB_TYPE_EMAIL_DYNAMIC_QUERY,
  MAX_RETRIES_LIMIT,
  QUERY_PARAMS_PLACEHOLDER,
  isFormTab,
  isPayloadDateRange,
} from '@app/constants/scheduled-job';
import { useGetAllDatasources, useGetAllDynamicQueries, useGetAppUsers } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { ColumnStyleConfig, DateRangeOption, FormTab, ScheduledJob } from '@app/types/scheduled-job';
import { IUser } from '@app/types/user';
import { useEffect, useMemo, useState } from 'react';
import {
  buildEmailPayload,
  extractRecipientUserIdsFromPayload,
  formatUserLabel,
  getDatasourceIdFromPayload,
  getQueryIdsFromPayload,
  normalizeUserId,
} from './scheduled-job-utils';
import { getDynamicQueryIdFromFileName } from '../datasources/dynamic-query-utils';

const getUserId = (user: IUser) => user.id;
const getUserSearchValue = (user: IUser) => `${user.first_name} ${user.last_name} ${user.email}`;
const selectedUsersCountLabel = (count: number) => `${count} users selected`;

const DATE_RANGE_OPTIONS: { value: DateRangeOption; label: string }[] = [
  { value: DATE_RANGE.NONE, label: 'None' },
  { value: DATE_RANGE.LAST_HOUR, label: 'Last hour' },
  { value: DATE_RANGE.LAST_DAY, label: 'Last day' },
  { value: DATE_RANGE.T_2, label: 'T-2 (2 days ago)' },
  { value: DATE_RANGE.LAST_7_DAYS, label: 'Last 7 days' },
  { value: DATE_RANGE.LAST_30_DAYS, label: 'Last 30 days' },
];

const isDateRangeOption = (value: string): value is DateRangeOption =>
  DATE_RANGE_OPTIONS.some((option) => option.value === value);

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
  const { data: dynamicQueries = [], isLoading: dynamicQueriesLoading } = useGetAllDynamicQueries(
    appId,
    datasourceId || undefined
  );

  const [cronExpr, setCronExpr] = useState(DEFAULT_CRON_EXPR);
  const [timezone, setTimezone] = useState(DEFAULT_TIMEZONE);
  const [selectedRecipientUserIds, setSelectedRecipientUserIds] = useState<string[]>([]);
  const [subject, setSubject] = useState('');
  const [emailContent, setEmailContent] = useState('');
  const [queryParamsJson, setQueryParamsJson] = useState('');
  const [columnStylesJson, setColumnStylesJson] = useState('');
  const [dateRange, setDateRange] = useState<DateRangeOption>(DATE_RANGE.NONE);
  const [startDateParamKey, setStartDateParamKey] = useState(DEFAULT_START_DATE_PARAM);
  const [endDateParamKey, setEndDateParamKey] = useState(DEFAULT_END_DATE_PARAM);
  const [maxRetries, setMaxRetries] = useState(DEFAULT_MAX_RETRIES);
  const [activeTab, setActiveTab] = useState<FormTab>(FORM_TAB.SCHEDULE);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const availableQueryIds = useMemo(
    () => dynamicQueries.map((query) => getDynamicQueryIdFromFileName(query.file)).filter((id) => id.length > 0),
    [dynamicQueries]
  );

  const toggleQueryId = (queryId: string) => {
    setSelectedQueryIds((prev) => (prev.includes(queryId) ? prev.filter((id) => id !== queryId) : [...prev, queryId]));
  };

  const resetForm = () => {
    setDatasourceId('');
    setSelectedQueryIds([]);
    setCronExpr(DEFAULT_CRON_EXPR);
    setTimezone(DEFAULT_TIMEZONE);
    setSelectedRecipientUserIds([]);
    setSubject('');
    setEmailContent('');
    setQueryParamsJson('');
    setColumnStylesJson('');
    setDateRange(DATE_RANGE.NONE);
    setStartDateParamKey(DEFAULT_START_DATE_PARAM);
    setEndDateParamKey(DEFAULT_END_DATE_PARAM);
    setMaxRetries(DEFAULT_MAX_RETRIES);
    setActiveTab(FORM_TAB.SCHEDULE);
    setError('');
  };

  const applyJobToForm = (existingJob: ScheduledJob) => {
    const payload = (existingJob.payload || {}) as Record<string, unknown>;
    setDatasourceId(getDatasourceIdFromPayload(payload));
    setSelectedQueryIds(getQueryIdsFromPayload(payload));
    setCronExpr(existingJob.cron_expr || DEFAULT_CRON_EXPR);
    setTimezone(existingJob.timezone || DEFAULT_TIMEZONE);
    setMaxRetries(String(existingJob.max_retries ?? Number(DEFAULT_MAX_RETRIES)));
    setSelectedRecipientUserIds(extractRecipientUserIdsFromPayload(payload));
    setSubject(typeof payload.subject === 'string' ? payload.subject : '');
    setEmailContent(typeof payload.email_content === 'string' ? payload.email_content : '');
    const paramsValue = payload.params;
    const dateRangeValue = payload.date_range;
    if (isPayloadDateRange(dateRangeValue)) {
      setDateRange(dateRangeValue);
    } else {
      setDateRange(DATE_RANGE.NONE);
    }
    setStartDateParamKey(
      typeof payload.start_date_param === 'string' ? payload.start_date_param : DEFAULT_START_DATE_PARAM
    );
    setEndDateParamKey(typeof payload.end_date_param === 'string' ? payload.end_date_param : DEFAULT_END_DATE_PARAM);
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
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    if (selectedQueryIds.length === 0) {
      setError('Select at least one dynamic query');
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    if (!cronExpr.trim()) {
      setError('Cron expression is required');
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    if (!timezone.trim()) {
      setError('Timezone is required');
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    if (selectedRecipientUserIds.length === 0) {
      setError('At least one recipient user is required');
      setActiveTab(FORM_TAB.EMAIL);
      return;
    }
    if (!Number.isInteger(retries) || retries < 0 || retries > MAX_RETRIES_LIMIT) {
      setError(`Max retries must be an integer between 0 and ${MAX_RETRIES_LIMIT}`);
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }

    let parsedParams: Record<string, unknown> | undefined;
    if (queryParamsJson.trim()) {
      try {
        const value = JSON.parse(queryParamsJson);
        if (typeof value !== 'object' || value === null || Array.isArray(value)) {
          setError('Query params must be a JSON object');
          setActiveTab(FORM_TAB.SCHEDULE);
          return;
        }
        parsedParams = value as Record<string, unknown>;
      } catch {
        setError('Query params must be valid JSON (object)');
        setActiveTab(FORM_TAB.SCHEDULE);
        return;
      }
    }

    let parsedColumnStyles: ColumnStyleConfig[] | undefined;
    if (columnStylesJson.trim()) {
      try {
        const value = JSON.parse(columnStylesJson);
        if (!Array.isArray(value)) {
          setError('Column styles must be a JSON array');
          setActiveTab(FORM_TAB.EMAIL);
          return;
        }
        parsedColumnStyles = value as ColumnStyleConfig[];
      } catch {
        setError('Column styles must be valid JSON (array)');
        setActiveTab(FORM_TAB.EMAIL);
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
      dateRange: dateRange === DATE_RANGE.NONE ? undefined : dateRange,
      startDateParam: dateRange === DATE_RANGE.NONE ? undefined : startDateParamKey.trim() || DEFAULT_START_DATE_PARAM,
      endDateParam: dateRange === DATE_RANGE.NONE ? undefined : endDateParamKey.trim() || DEFAULT_END_DATE_PARAM,
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
          job_type: JOB_TYPE_EMAIL_DYNAMIC_QUERY,
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

        <Tabs
          value={activeTab}
          onValueChange={(value) => {
            if (isFormTab(value)) setActiveTab(value);
          }}
        >
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value={FORM_TAB.SCHEDULE}>Schedule</TabsTrigger>
            <TabsTrigger value={FORM_TAB.EMAIL}>Email</TabsTrigger>
          </TabsList>

          <TabsContent value={FORM_TAB.SCHEDULE} className="mt-4 space-y-5">
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
                <Input
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(e.target.value)}
                  placeholder={DEFAULT_MAX_RETRIES}
                />
              </div>
            </div>

            <div>
              <p className="mb-2 text-xs text-[#878787]">
                Dynamic queries (select one or more — each becomes an attachment in the email)
              </p>
              {!datasourceId ? (
                <p className="text-sm text-[#878787]">Select a datasource to load queries.</p>
              ) : dynamicQueriesLoading ? (
                <p className="text-sm text-[#878787]">Loading queries...</p>
              ) : availableQueryIds.length === 0 ? (
                <p className="text-sm text-[#878787]">No dynamic queries found for this datasource.</p>
              ) : (
                <OptionChips options={availableQueryIds} selected={selectedQueryIds} onToggle={toggleQueryId} />
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="mb-1 text-xs text-[#878787]">Cron expression</p>
                <Input value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder={DEFAULT_CRON_EXPR} />
              </div>
              <div>
                <p className="mb-1 text-xs text-[#878787]">Timezone</p>
                <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder={DEFAULT_TIMEZONE} />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="mb-1 text-xs text-[#878787]">Dynamic date range (optional)</p>
                <Select
                  value={dateRange}
                  onValueChange={(value) => {
                    if (isDateRangeOption(value)) setDateRange(value);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select range" />
                  </SelectTrigger>
                  <SelectContent>
                    {DATE_RANGE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
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
                placeholder={QUERY_PARAMS_PLACEHOLDER}
                className="min-h-[90px] font-mono"
              />
            </div>
          </TabsContent>

          <TabsContent value={FORM_TAB.EMAIL} className="mt-4 space-y-5">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Subject (optional)</p>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Daily report" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1 flex items-center gap-1.5">
                  <p className="text-xs text-[#878787]">Email content (optional)</p>
                  <FieldHelp ariaLabel="Email content help" contentClassName="max-w-md">
                    Use {'{query_id}'} placeholders to embed result tables inline (e.g. {'{sales_summary}'}). Plain text
                    or HTML. Excel files are still attached when under the size limit. Leave empty for the default
                    summary.
                  </FieldHelp>
                </div>
                <Textarea
                  value={emailContent}
                  onChange={(e) => setEmailContent(e.target.value)}
                  placeholder={EMAIL_CONTENT_PLACEHOLDER}
                  className="min-h-[120px]"
                />
              </div>

              <div>
                <div className="mb-1 flex items-center gap-1.5">
                  <p className="text-xs text-[#878787]">Column styles (optional JSON)</p>
                  <FieldHelp ariaLabel="Column styles help">
                    Rules are evaluated top-to-bottom; first match wins.
                  </FieldHelp>
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
                <FieldHelp ariaLabel="Recipient users help">
                  Each user receives reports filtered by their data access (RLS).
                </FieldHelp>
              </div>
              <MultiSelect
                items={appUsers}
                selectedIds={selectedRecipientUserIds}
                onChange={setSelectedRecipientUserIds}
                getId={getUserId}
                getLabel={formatUserLabel}
                getSearchValue={getUserSearchValue}
                normalizeId={normalizeUserId}
                placeholder="Select recipient users"
                searchPlaceholder="Search users..."
                loading={appUsersLoading}
                loadingLabel="Loading users..."
                emptyLabel="No users found."
                showSelectAll
                selectedGroupHeading="Selected"
                allItemsGroupHeading="All users"
                selectedCountLabel={selectedUsersCountLabel}
              />
            </div>
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
