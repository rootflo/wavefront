import {
  DATE_RANGE,
  DEFAULT_CRON_EXPR,
  DEFAULT_END_DATE_PARAM,
  DEFAULT_MAX_RETRIES,
  DEFAULT_QUERY_LIMIT,
  DEFAULT_QUERY_OFFSET,
  DEFAULT_START_DATE_PARAM,
  DEFAULT_TIMEZONE,
  FORM_TAB,
  JOB_TYPE_EMAIL_DYNAMIC_QUERY,
  MAX_RETRIES_LIMIT,
} from '@app/constants/scheduled-job';
import {
  useCreateScheduledJob,
  useGetAllDatasources,
  useGetAllDynamicQueries,
  useGetAppUsers,
  useGetEmailConnections,
  useUpdateScheduledJob,
} from '@app/hooks';
import {
  ColumnStyleConfig,
  DateRangeOption,
  FormTab,
  QuerySpecFormOverrides,
  ScheduledJob,
} from '@app/types/scheduled-job';
import { useEffect, useMemo, useState } from 'react';
import {
  buildEmailPayload,
  extractQueryOverridesFromPayload,
  extractRecipientUserIdsFromPayload,
  getDatasourceIdFromPayload,
  getEmailConnectionIdFromPayload,
  toDateRangeOption,
} from './scheduled-job-utils';
import { getDynamicQueryIdFromFileName } from '../datasources/dynamic-query-utils';
import {
  QueryConfigEntry,
  createQueryConfigKey,
  createEmptyOverrides,
  createEmptyQueryConfig,
  parseOptionalNonNegativeInt,
  parseJsonObject,
  parseJsonArray,
} from './scheduled-job-form';

interface UseScheduledJobFormArgs {
  isOpen: boolean;
  appId: string;
  /** The job being edited; omit when creating one. */
  job?: ScheduledJob | null;
  onOpenChange: (open: boolean) => void;
}

/**
 * Every field of the scheduled job form, the data its pickers list, and saving: validates each tab in turn
 * (switching to the tab with the first problem) and builds the job's email payload.
 */
export const useScheduledJobForm = ({ isOpen, appId, job, onOpenChange }: UseScheduledJobFormArgs) => {
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
  const createScheduledJob = useCreateScheduledJob(appId);
  const updateScheduledJob = useUpdateScheduledJob(appId);
  const saving = createScheduledJob.isPending || updateScheduledJob.isPending;
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

  const handleSave = () => {
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

    setError('');
    const callbacks = {
      onSuccess: () => handleOpenChange(false),
      onError: () => setError('Unable to save scheduled job. Please verify the details and try again.'),
    };
    const fields = {
      cron_expr: cronExpr.trim(),
      timezone: timezone.trim(),
      max_retries: retries,
      payload: emailPayload,
    };
    if (isEditing && job) {
      updateScheduledJob.mutate({ jobId: job.id, request: fields }, callbacks);
    } else {
      createScheduledJob.mutate({ job_type: JOB_TYPE_EMAIL_DYNAMIC_QUERY, ...fields }, callbacks);
    }
  };

  return {
    job,
    isEditing,
    datasources,
    appUsers,
    appUsersLoading,
    datasourceId,
    setDatasourceId,
    queryConfigs,
    setQueryConfigs,
    expandedQueryKeys,
    setExpandedQueryKeys,
    jobDefaultsExpanded,
    setJobDefaultsExpanded,
    dynamicQueriesLoading,
    cronExpr,
    setCronExpr,
    timezone,
    setTimezone,
    selectedRecipientUserIds,
    setSelectedRecipientUserIds,
    emailConnectionId,
    subject,
    setSubject,
    emailContent,
    setEmailContent,
    queryParamsJson,
    setQueryParamsJson,
    columnStylesJson,
    setColumnStylesJson,
    filterExpr,
    setFilterExpr,
    queryLimit,
    setQueryLimit,
    queryOffset,
    setQueryOffset,
    dateRange,
    setDateRange,
    startDateParamKey,
    setStartDateParamKey,
    endDateParamKey,
    setEndDateParamKey,
    maxRetries,
    setMaxRetries,
    activeTab,
    setActiveTab,
    saving,
    error,
    availableQueryIds,
    selectedQueryIds,
    sendableConnections,
    handleSenderChange,
    updateQueryConfig,
    updateQueryConfigOverrides,
    toggleQueryExpanded,
    addQueryConfig,
    removeQueryConfig,
    queryOptionsForConfig,
    handleOpenChange,
    handleSave,
  };
};

export type ScheduledJobFormState = ReturnType<typeof useScheduledJobForm>;
