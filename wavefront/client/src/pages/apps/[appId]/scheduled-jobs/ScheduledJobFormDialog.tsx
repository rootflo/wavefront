import floConsoleService from '@app/api';
import MultiSelect from '@app/components/MultiSelect';
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
  DEFAULT_QUERY_LIMIT,
  DEFAULT_QUERY_OFFSET,
  DEFAULT_START_DATE_PARAM,
  DEFAULT_TIMEZONE,
  EMAIL_CONTENT_PLACEHOLDER,
  FILTER_PLACEHOLDER,
  FORM_TAB,
  JOB_TYPE_EMAIL_DYNAMIC_QUERY,
  MAX_RETRIES_LIMIT,
  QUERY_PARAMS_PLACEHOLDER,
  isFormTab,
} from '@app/constants/scheduled-job';
import { useGetAllDatasources, useGetAllDynamicQueries, useGetAppUsers, useGetEmailConnections } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import {
  ColumnStyleConfig,
  DateRangeOption,
  FormTab,
  QuerySpecFormOverrides,
  ScheduledJob,
} from '@app/types/scheduled-job';
import { IUser } from '@app/types/user';
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  buildEmailPayload,
  extractQueryOverridesFromPayload,
  extractRecipientUserIdsFromPayload,
  formatUserLabel,
  getDatasourceIdFromPayload,
  getEmailConnectionIdFromPayload,
  normalizeUserId,
  toDateRangeOption,
} from './scheduled-job-utils';
import { getDynamicQueryIdFromFileName } from '../datasources/dynamic-query-utils';

const getUserId = (user: IUser) => user.id;
const getUserSearchValue = (user: IUser) => `${user.first_name} ${user.last_name} ${user.email}`;
const selectedUsersCountLabel = (count: number) => `${count} users selected`;

type QueryConfigEntry = {
  key: string;
  queryId: string;
  overrides: QuerySpecFormOverrides;
};

const createQueryConfigKey = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `query-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

const createEmptyOverrides = (): QuerySpecFormOverrides => ({ date_range: DATE_RANGE.NONE });

const createEmptyQueryConfig = (): QueryConfigEntry => ({
  key: createQueryConfigKey(),
  queryId: '',
  overrides: createEmptyOverrides(),
});

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

const parseOptionalNonNegativeInt = (
  value: string,
  fieldLabel: string
): { ok: true; value?: number } | { ok: false; error: string } => {
  if (!value.trim()) return { ok: true, value: undefined };
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    return { ok: false, error: `${fieldLabel} must be a non-negative integer` };
  }
  return { ok: true, value: parsed };
};

const parseJsonObject = (
  value: string,
  fieldLabel: string
): { ok: true; value?: Record<string, unknown> } | { ok: false; error: string } => {
  if (!value.trim()) return { ok: true, value: undefined };
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { ok: false, error: `${fieldLabel} must be a JSON object` };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch {
    return { ok: false, error: `${fieldLabel} must be valid JSON (object)` };
  }
};

const parseJsonArray = (
  value: string,
  fieldLabel: string
): { ok: true; value?: ColumnStyleConfig[] } | { ok: false; error: string } => {
  if (!value.trim()) return { ok: true, value: undefined };
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return { ok: false, error: `${fieldLabel} must be a JSON array` };
    }
    return { ok: true, value: parsed as ColumnStyleConfig[] };
  } catch {
    return { ok: false, error: `${fieldLabel} must be valid JSON (array)` };
  }
};

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
  const { data: emailConnections = [] } = useGetEmailConnections(appId);

  const [datasourceId, setDatasourceId] = useState('');
  const [queryConfigs, setQueryConfigs] = useState<QueryConfigEntry[]>([]);
  const [expandedQueryKeys, setExpandedQueryKeys] = useState<Set<string>>(new Set());
  const [jobDefaultsExpanded, setJobDefaultsExpanded] = useState(false);
  const { data: dynamicQueries = [], isLoading: dynamicQueriesLoading } = useGetAllDynamicQueries(
    appId,
    datasourceId || undefined
  );

  const [cronExpr, setCronExpr] = useState(DEFAULT_CRON_EXPR);
  const [timezone, setTimezone] = useState(DEFAULT_TIMEZONE);
  const [selectedRecipientUserIds, setSelectedRecipientUserIds] = useState<string[]>([]);
  const [emailConnectionId, setEmailConnectionId] = useState('');
  const [subject, setSubject] = useState('');
  const [emailContent, setEmailContent] = useState('');
  const [queryParamsJson, setQueryParamsJson] = useState('');
  const [columnStylesJson, setColumnStylesJson] = useState('');
  const [filterExpr, setFilterExpr] = useState('');
  const [queryLimit, setQueryLimit] = useState(DEFAULT_QUERY_LIMIT);
  const [queryOffset, setQueryOffset] = useState(DEFAULT_QUERY_OFFSET);
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

  const selectedQueryIds = useMemo(
    () => queryConfigs.map((config) => config.queryId).filter((id) => id.length > 0),
    [queryConfigs]
  );

  const sendableConnections = useMemo(
    () => emailConnections.filter((connection) => connection.status === 'active'),
    [emailConnections]
  );

  const handleSenderChange = (value: string) => {
    setEmailConnectionId(value);
  };

  const updateQueryConfig = (key: string, patch: Partial<QueryConfigEntry>) => {
    setQueryConfigs((prev) => prev.map((config) => (config.key === key ? { ...config, ...patch } : config)));
  };

  const updateQueryConfigOverrides = (key: string, patch: Partial<QuerySpecFormOverrides>) => {
    setQueryConfigs((prev) =>
      prev.map((config) => (config.key === key ? { ...config, overrides: { ...config.overrides, ...patch } } : config))
    );
  };

  const toggleQueryExpanded = (key: string) => {
    setExpandedQueryKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const addQueryConfig = () => {
    const entry = createEmptyQueryConfig();
    setQueryConfigs((prev) => [...prev, entry]);
    setExpandedQueryKeys((prev) => new Set(prev).add(entry.key));
  };

  const removeQueryConfig = (key: string) => {
    setQueryConfigs((prev) => prev.filter((config) => config.key !== key));
    setExpandedQueryKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  };

  const queryOptionsForConfig = (configKey: string, currentQueryId: string) => {
    const usedIds = new Set(
      queryConfigs.filter((config) => config.key !== configKey && config.queryId).map((config) => config.queryId)
    );
    return availableQueryIds.filter((id) => id === currentQueryId || !usedIds.has(id));
  };

  const resetForm = () => {
    setDatasourceId('');
    setQueryConfigs([]);
    setExpandedQueryKeys(new Set());
    setJobDefaultsExpanded(false);
    setCronExpr(DEFAULT_CRON_EXPR);
    setTimezone(DEFAULT_TIMEZONE);
    setSelectedRecipientUserIds([]);
    setEmailConnectionId('');
    setSubject('');
    setEmailContent('');
    setQueryParamsJson('');
    setColumnStylesJson('');
    setFilterExpr('');
    setQueryLimit(DEFAULT_QUERY_LIMIT);
    setQueryOffset(DEFAULT_QUERY_OFFSET);
    setDateRange(DATE_RANGE.NONE);
    setStartDateParamKey(DEFAULT_START_DATE_PARAM);
    setEndDateParamKey(DEFAULT_END_DATE_PARAM);
    setMaxRetries(DEFAULT_MAX_RETRIES);
    setActiveTab(FORM_TAB.SCHEDULE);
    setError('');
  };

  const applyJobToForm = (existingJob: ScheduledJob) => {
    const payload = (existingJob.payload || {}) as Record<string, unknown>;
    const { queryIds, overrides } = extractQueryOverridesFromPayload(payload);
    setDatasourceId(getDatasourceIdFromPayload(payload));
    setQueryConfigs(
      queryIds.map((queryId) => ({
        key: createQueryConfigKey(),
        queryId,
        overrides: overrides[queryId] ?? createEmptyOverrides(),
      }))
    );
    setExpandedQueryKeys(new Set());
    setJobDefaultsExpanded(false);
    setCronExpr(existingJob.cron_expr || DEFAULT_CRON_EXPR);
    setTimezone(existingJob.timezone || DEFAULT_TIMEZONE);
    setMaxRetries(String(existingJob.max_retries ?? Number(DEFAULT_MAX_RETRIES)));
    setSelectedRecipientUserIds(extractRecipientUserIdsFromPayload(payload));
    setEmailConnectionId(getEmailConnectionIdFromPayload(payload));
    setSubject(typeof payload.subject === 'string' ? payload.subject : '');
    setEmailContent(typeof payload.email_content === 'string' ? payload.email_content : '');
    setFilterExpr(typeof payload.filter === 'string' ? payload.filter : '');
    setQueryLimit(typeof payload.limit === 'number' ? String(payload.limit) : DEFAULT_QUERY_LIMIT);
    setQueryOffset(typeof payload.offset === 'number' ? String(payload.offset) : DEFAULT_QUERY_OFFSET);
    setDateRange(toDateRangeOption(payload.date_range));
    setStartDateParamKey(
      typeof payload.start_date_param === 'string' ? payload.start_date_param : DEFAULT_START_DATE_PARAM
    );
    setEndDateParamKey(typeof payload.end_date_param === 'string' ? payload.end_date_param : DEFAULT_END_DATE_PARAM);

    const paramsValue = payload.params;
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
    if (!Number.isInteger(retries) || retries < 0 || retries > MAX_RETRIES_LIMIT) {
      setError(`Max retries must be an integer between 0 and ${MAX_RETRIES_LIMIT}`);
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    if (!datasourceId.trim()) {
      setError('Datasource is required');
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    if (queryConfigs.length === 0) {
      setError('Add at least one query configuration');
      setActiveTab(FORM_TAB.QUERY);
      return;
    }
    if (queryConfigs.some((config) => !config.queryId.trim())) {
      setError('Select a query for every query configuration');
      setActiveTab(FORM_TAB.QUERY);
      return;
    }
    if (selectedQueryIds.length === 0) {
      setError('Select at least one dynamic query');
      setActiveTab(FORM_TAB.QUERY);
      return;
    }

    const limitResult = parseOptionalNonNegativeInt(queryLimit, 'Row limit');
    if (!limitResult.ok) {
      setError(limitResult.error);
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }
    const offsetResult = parseOptionalNonNegativeInt(queryOffset, 'Offset');
    if (!offsetResult.ok) {
      setError(offsetResult.error);
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }

    const paramsResult = parseJsonObject(queryParamsJson, 'Query params');
    if (!paramsResult.ok) {
      setError(paramsResult.error);
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }

    const columnStylesResult = parseJsonArray(columnStylesJson, 'Column styles');
    if (!columnStylesResult.ok) {
      setError(columnStylesResult.error);
      setActiveTab(FORM_TAB.SCHEDULE);
      return;
    }

    const queryOverrides: Record<string, QuerySpecFormOverrides> = {};
    const queryOverrideParams: Record<string, Record<string, unknown> | undefined> = {};
    const queryOverrideColumnStyles: Record<string, ColumnStyleConfig[] | undefined> = {};

    for (const config of queryConfigs) {
      const queryId = config.queryId.trim();
      const overrides = config.overrides;
      queryOverrides[queryId] = overrides;

      const queryLimitResult = parseOptionalNonNegativeInt(overrides.limit ?? '', `Limit for ${queryId}`);
      if (!queryLimitResult.ok) {
        setError(queryLimitResult.error);
        setActiveTab(FORM_TAB.QUERY);
        return;
      }
      const queryOffsetResult = parseOptionalNonNegativeInt(overrides.offset ?? '', `Offset for ${queryId}`);
      if (!queryOffsetResult.ok) {
        setError(queryOffsetResult.error);
        setActiveTab(FORM_TAB.QUERY);
        return;
      }

      const queryParamsResult = parseJsonObject(overrides.paramsJson ?? '', `Params for ${queryId}`);
      if (!queryParamsResult.ok) {
        setError(queryParamsResult.error);
        setActiveTab(FORM_TAB.QUERY);
        return;
      }
      queryOverrideParams[queryId] = queryParamsResult.value;

      const queryStylesResult = parseJsonArray(overrides.columnStylesJson ?? '', `Column styles for ${queryId}`);
      if (!queryStylesResult.ok) {
        setError(queryStylesResult.error);
        setActiveTab(FORM_TAB.QUERY);
        return;
      }
      queryOverrideColumnStyles[queryId] = queryStylesResult.value;
    }

    if (selectedRecipientUserIds.length === 0) {
      setError('At least one recipient user is required');
      setActiveTab(FORM_TAB.EMAIL);
      return;
    }
    if (!emailConnectionId) {
      setError('Select an email connection to send from');
      setActiveTab(FORM_TAB.EMAIL);
      return;
    }

    const emailPayload = buildEmailPayload({
      datasourceId: datasourceId.trim(),
      queryIds: selectedQueryIds,
      queryOverrides,
      queryOverrideParams,
      queryOverrideColumnStyles,
      recipientUserIds: selectedRecipientUserIds,
      emailConnectionId,
      subject: subject.trim() || undefined,
      emailContent: emailContent.trim() || undefined,
      columnStyles: columnStylesResult.value,
      dateRange: dateRange === DATE_RANGE.NONE ? undefined : dateRange,
      startDateParam: dateRange === DATE_RANGE.NONE ? undefined : startDateParamKey.trim() || DEFAULT_START_DATE_PARAM,
      endDateParam: dateRange === DATE_RANGE.NONE ? undefined : endDateParamKey.trim() || DEFAULT_END_DATE_PARAM,
      params: paramsResult.value,
      filter: filterExpr.trim() || undefined,
      offset: offsetResult.value,
      limit: limitResult.value,
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

  const renderDateRangeFields = (
    value: DateRangeOption,
    onDateRangeChange: (next: DateRangeOption) => void,
    startKey: string,
    onStartKeyChange: (next: string) => void,
    endKey: string,
    onEndKeyChange: (next: string) => void
  ) => (
    <div className="grid grid-cols-3 gap-3">
      <div>
        <p className="mb-1 text-xs text-[#878787]">Dynamic date range (optional)</p>
        <Select
          value={value}
          onValueChange={(next) => {
            if (isDateRangeOption(next)) onDateRangeChange(next);
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
        <Input value={startKey} onChange={(e) => onStartKeyChange(e.target.value)} />
      </div>
      <div>
        <p className="mb-1 text-xs text-[#878787]">End date param key</p>
        <Input value={endKey} onChange={(e) => onEndKeyChange(e.target.value)} />
      </div>
    </div>
  );

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="flex h-[760px] max-h-[760px] max-w-4xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
        <DialogHeader className="shrink-0">
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
          className="flex min-h-0 flex-1 flex-col overflow-hidden"
        >
          <TabsList className="grid w-full shrink-0 grid-cols-3">
            <TabsTrigger value={FORM_TAB.SCHEDULE}>Job setup</TabsTrigger>
            <TabsTrigger value={FORM_TAB.QUERY}>Queries</TabsTrigger>
            <TabsTrigger value={FORM_TAB.EMAIL}>Email</TabsTrigger>
          </TabsList>

          <TabsContent value={FORM_TAB.SCHEDULE} className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
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

            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="mb-1 text-xs text-[#878787]">Datasource</p>
                <Select
                  value={datasourceId}
                  onValueChange={(value) => {
                    setDatasourceId(value);
                    if (!job || getDatasourceIdFromPayload(job.payload || {}) !== value) {
                      setQueryConfigs([]);
                      setExpandedQueryKeys(new Set());
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
              <p className="mb-2 text-xs text-[#878787]">Selected queries</p>
              {selectedQueryIds.length === 0 ? (
                <p className="text-sm text-[#878787]">No queries selected yet. Choose them on the Query tab.</p>
              ) : (
                <div className="frost-glass border-frost-border flex max-h-28 flex-wrap gap-2 overflow-y-auto rounded-md border p-3">
                  {selectedQueryIds.map((queryId) => (
                    <span
                      key={queryId}
                      className="frost-glass-strong frost-text border-frost-border rounded-full border px-3 py-1 text-xs"
                    >
                      {queryId}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="border-frost-border overflow-hidden rounded-md border">
              <button
                type="button"
                className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left"
                onClick={() => setJobDefaultsExpanded((prev) => !prev)}
                aria-expanded={jobDefaultsExpanded}
              >
                <ChevronDown
                  className={`frost-text-muted h-4 w-4 shrink-0 transition-transform ${jobDefaultsExpanded ? 'rotate-0' : '-rotate-90'}`}
                />
                <div className="min-w-0">
                  <p className="frost-text truncate text-sm font-medium">Job-level query defaults</p>
                  <p className="truncate text-xs text-[#878787]">
                    Applied to every selected query unless overridden on the Query tab.
                  </p>
                </div>
              </button>

              {jobDefaultsExpanded ? (
                <div className="border-frost-border space-y-4 border-t px-4 py-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="mb-1 text-xs text-[#878787]">Row limit</p>
                      <Input
                        value={queryLimit}
                        onChange={(e) => setQueryLimit(e.target.value)}
                        placeholder={DEFAULT_QUERY_LIMIT}
                      />
                    </div>
                    <div>
                      <p className="mb-1 text-xs text-[#878787]">Offset</p>
                      <Input
                        value={queryOffset}
                        onChange={(e) => setQueryOffset(e.target.value)}
                        placeholder={DEFAULT_QUERY_OFFSET}
                      />
                    </div>
                  </div>

                  <div>
                    <p className="mb-1 text-xs text-[#878787]">Filter expression (optional)</p>
                    <Input
                      value={filterExpr}
                      onChange={(e) => setFilterExpr(e.target.value)}
                      placeholder={FILTER_PLACEHOLDER}
                    />
                  </div>

                  {renderDateRangeFields(
                    dateRange,
                    setDateRange,
                    startDateParamKey,
                    setStartDateParamKey,
                    endDateParamKey,
                    setEndDateParamKey
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="mb-1 text-xs text-[#878787]">Query params (optional JSON)</p>
                      <Textarea
                        value={queryParamsJson}
                        onChange={(e) => setQueryParamsJson(e.target.value)}
                        placeholder={QUERY_PARAMS_PLACEHOLDER}
                        className="min-h-[90px] font-mono"
                      />
                    </div>
                    <div>
                      <p className="mb-1 text-xs text-[#878787]">Column styles (optional JSON)</p>
                      <Textarea
                        value={columnStylesJson}
                        onChange={(e) => setColumnStylesJson(e.target.value)}
                        placeholder={COLUMN_STYLES_PLACEHOLDER}
                        className="min-h-[90px] font-mono text-xs"
                      />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </TabsContent>

          <TabsContent value={FORM_TAB.QUERY} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="frost-text text-sm font-medium">Query configurations</p>
                <p className="text-xs text-[#878787]">
                  Add a query, then optionally override job-level defaults. Leave fields empty to inherit.
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addQueryConfig}
                disabled={!datasourceId || dynamicQueriesLoading || availableQueryIds.length === 0}
              >
                <Plus className="mr-1 h-4 w-4" />
                Add query
              </Button>
            </div>

            {!datasourceId ? (
              <p className="text-sm text-[#878787]">Select a datasource on the Job setup tab to load queries.</p>
            ) : dynamicQueriesLoading ? (
              <p className="text-sm text-[#878787]">Loading queries...</p>
            ) : availableQueryIds.length === 0 ? (
              <p className="text-sm text-[#878787]">No dynamic queries found for this datasource.</p>
            ) : queryConfigs.length === 0 ? (
              <button
                type="button"
                onClick={addQueryConfig}
                className="border-frost-border frost-text-muted hover:frost-text hover:bg-frost-glass-strong flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-4 py-8 text-sm transition-colors"
              >
                <Plus className="h-4 w-4" />
                Add your first query configuration
              </button>
            ) : (
              <div className="space-y-3">
                {queryConfigs.map((config, index) => {
                  const isExpanded = expandedQueryKeys.has(config.key);
                  const overrides = config.overrides;
                  const title = config.queryId || `Query ${index + 1}`;
                  const queryOptions = queryOptionsForConfig(config.key, config.queryId);

                  return (
                    <div key={config.key} className="border-frost-border overflow-hidden rounded-md border">
                      <div className="flex items-center gap-2 px-3 py-2">
                        <button
                          type="button"
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
                          onClick={() => toggleQueryExpanded(config.key)}
                          aria-expanded={isExpanded}
                        >
                          <ChevronDown
                            className={`frost-text-muted h-4 w-4 shrink-0 transition-transform ${isExpanded ? 'rotate-0' : '-rotate-90'}`}
                          />
                          <span className="frost-text truncate text-sm font-medium">{title}</span>
                          {!config.queryId ? (
                            <span className="frost-text-muted shrink-0 text-xs">Select a query</span>
                          ) : null}
                        </button>
                        <button
                          type="button"
                          className="frost-text-muted rounded-md p-1.5 transition-colors hover:text-red-500"
                          aria-label={`Remove ${title}`}
                          onClick={() => removeQueryConfig(config.key)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>

                      {isExpanded ? (
                        <div className="border-frost-border space-y-3 border-t px-4 py-4">
                          <div>
                            <p className="mb-1 text-xs text-[#878787]">Query</p>
                            <Select
                              value={config.queryId || undefined}
                              onValueChange={(value) => updateQueryConfig(config.key, { queryId: value })}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="Select a query" />
                              </SelectTrigger>
                              <SelectContent>
                                {queryOptions.map((queryId) => (
                                  <SelectItem key={queryId} value={queryId}>
                                    {queryId}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>

                          <div>
                            <p className="mb-1 text-xs text-[#878787]">Datasource override (optional)</p>
                            <Select
                              value={overrides.datasource_id || '__inherit__'}
                              onValueChange={(value) =>
                                updateQueryConfigOverrides(config.key, {
                                  datasource_id: value === '__inherit__' ? '' : value,
                                })
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="Inherit job datasource" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="__inherit__">Inherit job datasource</SelectItem>
                                {datasources.map((ds) => (
                                  <SelectItem key={ds.id} value={ds.id}>
                                    {ds.name || ds.id}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>

                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <p className="mb-1 text-xs text-[#878787]">Row limit override</p>
                              <Input
                                value={overrides.limit ?? ''}
                                onChange={(e) => updateQueryConfigOverrides(config.key, { limit: e.target.value })}
                                placeholder="Inherit"
                              />
                            </div>
                            <div>
                              <p className="mb-1 text-xs text-[#878787]">Offset override</p>
                              <Input
                                value={overrides.offset ?? ''}
                                onChange={(e) => updateQueryConfigOverrides(config.key, { offset: e.target.value })}
                                placeholder="Inherit"
                              />
                            </div>
                          </div>

                          <div>
                            <p className="mb-1 text-xs text-[#878787]">Filter override (optional)</p>
                            <Input
                              value={overrides.filter ?? ''}
                              onChange={(e) => updateQueryConfigOverrides(config.key, { filter: e.target.value })}
                              placeholder="Inherit"
                            />
                          </div>

                          {renderDateRangeFields(
                            overrides.date_range ?? DATE_RANGE.NONE,
                            (next) => updateQueryConfigOverrides(config.key, { date_range: next }),
                            overrides.start_date_param ?? DEFAULT_START_DATE_PARAM,
                            (next) => updateQueryConfigOverrides(config.key, { start_date_param: next }),
                            overrides.end_date_param ?? DEFAULT_END_DATE_PARAM,
                            (next) => updateQueryConfigOverrides(config.key, { end_date_param: next })
                          )}

                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <p className="mb-1 text-xs text-[#878787]">Params override (optional JSON)</p>
                              <Textarea
                                value={overrides.paramsJson ?? ''}
                                onChange={(e) => updateQueryConfigOverrides(config.key, { paramsJson: e.target.value })}
                                placeholder={QUERY_PARAMS_PLACEHOLDER}
                                className="min-h-20 font-mono text-xs"
                              />
                            </div>
                            <div>
                              <p className="mb-1 text-xs text-[#878787]">Column styles override (optional JSON)</p>
                              <Textarea
                                value={overrides.columnStylesJson ?? ''}
                                onChange={(e) =>
                                  updateQueryConfigOverrides(config.key, { columnStylesJson: e.target.value })
                                }
                                placeholder={COLUMN_STYLES_PLACEHOLDER}
                                className="min-h-20 font-mono text-xs"
                              />
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  );
                })}

                <button
                  type="button"
                  onClick={addQueryConfig}
                  disabled={availableQueryIds.length > 0 && selectedQueryIds.length >= availableQueryIds.length}
                  className="border-frost-border frost-text-muted hover:frost-text hover:bg-frost-glass-strong flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-3 py-3 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Plus className="h-4 w-4" />
                  Add another query
                </button>
              </div>
            )}
          </TabsContent>

          <TabsContent value={FORM_TAB.EMAIL} className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
            <div>
              <p className="mb-1 text-xs text-[#878787]">Subject (optional)</p>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Daily report" />
            </div>

            <div>
              <p className="mb-1 text-xs text-[#878787]">Send from</p>
              <Select value={emailConnectionId || undefined} onValueChange={handleSenderChange}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a mailbox" />
                </SelectTrigger>
                <SelectContent>
                  {sendableConnections.map((connection) => (
                    <SelectItem key={connection.id} value={connection.id}>
                      {connection.name} ({connection.mailbox_email})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <p className="mb-1 text-xs text-[#878787]">Email content (optional)</p>
              <Textarea
                value={emailContent}
                onChange={(e) => setEmailContent(e.target.value)}
                placeholder={EMAIL_CONTENT_PLACEHOLDER}
                className="min-h-[120px]"
              />
            </div>

            <div>
              <p className="mb-1 text-xs text-[#878787]">Recipient users</p>
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

        {error ? <p className="shrink-0 text-sm text-red-500">{error}</p> : null}

        <DialogFooter className="shrink-0">
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
