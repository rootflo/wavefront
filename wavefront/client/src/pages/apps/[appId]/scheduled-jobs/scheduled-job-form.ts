import {
  DATE_RANGE,
  DEFAULT_CRON_EXPR,
  DEFAULT_END_DATE_PARAM,
  DEFAULT_MAX_RETRIES,
  DEFAULT_QUERY_LIMIT,
  DEFAULT_QUERY_OFFSET,
  DEFAULT_START_DATE_PARAM,
  DEFAULT_TIMEZONE,
  JOB_TYPE_EMAIL_DYNAMIC_QUERY,
  JOB_TYPE_SCHEDULED_QUERY,
  MAX_RETRIES_LIMIT,
  PAYLOAD_DATE_RANGES,
  isScheduledJobType,
} from '@app/constants/scheduled-job';
import {
  ColumnStyleConfig,
  DateRangeOption,
  ScheduledJob,
  ScheduledJobEmailPayload,
  ScheduledJobQueryPayload,
  ScheduledJobQuerySpec,
} from '@app/types/scheduled-job';
import { IUser } from '@app/types/user';
import { z } from 'zod';
import {
  extractRecipientUserIdsFromPayload,
  getDatasourceIdFromPayload,
  getEmailConnectionIdFromPayload,
  toDateRangeOption,
} from './scheduled-job-utils';

// The scheduled job form: its zod schema, and conversion between form values and the job payload.

/** The compact label style the scheduled job form uses for every field. */
export const FIELD_STYLE = { className: 'space-y-1', labelClassName: 'frost-text-muted text-xs font-normal' };

export const getUserId = (user: IUser) => user.id;
export const getUserSearchValue = (user: IUser) => `${user.first_name} ${user.last_name} ${user.email}`;
export const selectedUsersCountLabel = (count: number) => `${count} users selected`;

export const DATE_RANGE_OPTIONS: { value: DateRangeOption; label: string }[] = [
  { value: DATE_RANGE.NONE, label: 'None' },
  { value: DATE_RANGE.LAST_HOUR, label: 'Last hour' },
  { value: DATE_RANGE.LAST_DAY, label: 'Last day' },
  { value: DATE_RANGE.T_2, label: 'T-2 (2 days ago)' },
  { value: DATE_RANGE.LAST_7_DAYS, label: 'Last 7 days' },
  { value: DATE_RANGE.LAST_30_DAYS, label: 'Last 30 days' },
];

export const parseOptionalNonNegativeInt = (
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

export const parseJsonObject = (
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

export const parseJsonArray = (
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

/** A text field that must pass one of the parsers above; blank always passes. */
const parsedField = (parse: (value: string) => { ok: true } | { ok: false; error: string }) =>
  z.string().superRefine((value, ctx) => {
    const result = parse(value);
    if (!result.ok) ctx.addIssue({ code: z.ZodIssueCode.custom, message: result.error });
  });

/** Query settings, set once for the job and optionally overridden per query (blank = inherit). */
const querySettingsShape = {
  filter: z.string(),
  limit: parsedField((v) => parseOptionalNonNegativeInt(v, 'Row limit')),
  offset: parsedField((v) => parseOptionalNonNegativeInt(v, 'Offset')),
  dateRange: z.enum([DATE_RANGE.NONE, ...PAYLOAD_DATE_RANGES]),
  startDateParam: z.string(),
  endDateParam: z.string(),
  paramsJson: parsedField((v) => parseJsonObject(v, 'Query params')),
  columnStylesJson: parsedField((v) => parseJsonArray(v, 'Column styles')),
};

export const scheduledJobFormSchema = z
  .object({
    jobType: z.enum([JOB_TYPE_EMAIL_DYNAMIC_QUERY, JOB_TYPE_SCHEDULED_QUERY]),
    cronExpr: z.string().trim().min(1, 'Cron expression is required'),
    timezone: z.string().trim().min(1, 'Timezone is required'),
    maxRetries: z.string().refine((value) => {
      const retries = Number(value);
      return value.trim() !== '' && Number.isInteger(retries) && retries >= 0 && retries <= MAX_RETRIES_LIMIT;
    }, `Max retries must be an integer between 0 and ${MAX_RETRIES_LIMIT}`),
    datasourceId: z.string().min(1, 'Datasource is required'),
    defaults: z.object(querySettingsShape),
    queries: z
      .array(
        z.object({
          queryId: z.string().min(1, 'Select a query'),
          overrides: z.object({ ...querySettingsShape, datasourceId: z.string() }),
        })
      )
      .min(1, 'Add at least one query'),
    recipientUserIds: z.array(z.string()),
    emailConnectionId: z.string(),
    subject: z.string(),
    emailContent: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.jobType !== JOB_TYPE_EMAIL_DYNAMIC_QUERY) return;
    if (values.recipientUserIds.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['recipientUserIds'],
        message: 'At least one recipient user is required',
      });
    }
    if (!values.emailConnectionId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['emailConnectionId'],
        message: 'Select an email connection to send from',
      });
    }
  });

export type ScheduledJobFormValues = z.infer<typeof scheduledJobFormSchema>;
export type QuerySettingsValues = ScheduledJobFormValues['defaults'];
export type QueryEntryValues = ScheduledJobFormValues['queries'][number];

const emptySettings = (): QuerySettingsValues => ({
  filter: '',
  limit: '',
  offset: '',
  dateRange: DATE_RANGE.NONE,
  startDateParam: DEFAULT_START_DATE_PARAM,
  endDateParam: DEFAULT_END_DATE_PARAM,
  paramsJson: '',
  columnStylesJson: '',
});

export const createEmptyQueryEntry = (): QueryEntryValues => ({
  queryId: '',
  overrides: { ...emptySettings(), datasourceId: '' },
});

// ---- payload -> form values ----

const asString = (value: unknown): string => (typeof value === 'string' ? value : '');
const intToString = (value: unknown): string =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0 ? String(value) : '';
const objectToJson = (value: unknown): string =>
  value && typeof value === 'object' && !Array.isArray(value) ? JSON.stringify(value, null, 2) : '';
const arrayToJson = (value: unknown): string =>
  Array.isArray(value) && value.length > 0 ? JSON.stringify(value, null, 2) : '';

const settingsFromPayload = (raw: Record<string, unknown>): QuerySettingsValues => ({
  filter: asString(raw.filter),
  limit: intToString(raw.limit),
  offset: intToString(raw.offset),
  dateRange: toDateRangeOption(raw.date_range),
  startDateParam: asString(raw.start_date_param) || DEFAULT_START_DATE_PARAM,
  endDateParam: asString(raw.end_date_param) || DEFAULT_END_DATE_PARAM,
  paramsJson: objectToJson(raw.params),
  columnStylesJson: arrayToJson(raw.column_styles),
});

const queriesFromPayload = (payload: Record<string, unknown>): QueryEntryValues[] => {
  if (!Array.isArray(payload.queries)) return [];
  return payload.queries.flatMap((item): QueryEntryValues[] => {
    if (!item || typeof item !== 'object') return [];
    const raw = item as Record<string, unknown>;
    const queryId = asString(raw.query_id).trim();
    if (!queryId) return [];
    return [{ queryId, overrides: { ...settingsFromPayload(raw), datasourceId: asString(raw.datasource_id).trim() } }];
  });
};

/** Form values for a job being edited, or the defaults for a new one. */
export const toFormValues = (job?: ScheduledJob | null): ScheduledJobFormValues => {
  if (!job) {
    return {
      jobType: JOB_TYPE_EMAIL_DYNAMIC_QUERY,
      cronExpr: DEFAULT_CRON_EXPR,
      timezone: DEFAULT_TIMEZONE,
      maxRetries: DEFAULT_MAX_RETRIES,
      datasourceId: '',
      defaults: { ...emptySettings(), limit: DEFAULT_QUERY_LIMIT, offset: DEFAULT_QUERY_OFFSET },
      queries: [],
      recipientUserIds: [],
      emailConnectionId: '',
      subject: '',
      emailContent: '',
    };
  }
  const payload = (job.payload || {}) as Record<string, unknown>;
  const defaults = settingsFromPayload(payload);
  return {
    jobType: isScheduledJobType(job.job_type) ? job.job_type : JOB_TYPE_EMAIL_DYNAMIC_QUERY,
    cronExpr: job.cron_expr || DEFAULT_CRON_EXPR,
    timezone: job.timezone || DEFAULT_TIMEZONE,
    maxRetries: String(job.max_retries ?? DEFAULT_MAX_RETRIES),
    datasourceId: getDatasourceIdFromPayload(payload),
    defaults: {
      ...defaults,
      limit: defaults.limit || DEFAULT_QUERY_LIMIT,
      offset: defaults.offset || DEFAULT_QUERY_OFFSET,
    },
    queries: queriesFromPayload(payload),
    recipientUserIds: extractRecipientUserIdsFromPayload(payload),
    emailConnectionId: getEmailConnectionIdFromPayload(payload),
    subject: asString(payload.subject),
    emailContent: asString(payload.email_content),
  };
};

// ---- form values -> payload (values have passed the schema, so parsing cannot fail) ----

const parsedValue = <T>(result: { ok: true; value?: T } | { ok: false }): T | undefined =>
  result.ok ? result.value : undefined;

/** The settings as payload fields; blank fields are left out so they inherit. */
const settingsToPayload = (settings: QuerySettingsValues, includeColumnStyles: boolean) => {
  const hasRange = settings.dateRange !== DATE_RANGE.NONE;
  return {
    filter: settings.filter.trim() || undefined,
    offset: parsedValue(parseOptionalNonNegativeInt(settings.offset, '')),
    limit: parsedValue(parseOptionalNonNegativeInt(settings.limit, '')),
    params: parsedValue(parseJsonObject(settings.paramsJson, '')),
    column_styles: includeColumnStyles ? parsedValue(parseJsonArray(settings.columnStylesJson, '')) : undefined,
    date_range: settings.dateRange === DATE_RANGE.NONE ? undefined : settings.dateRange,
    start_date_param: hasRange ? settings.startDateParam.trim() || DEFAULT_START_DATE_PARAM : undefined,
    end_date_param: hasRange ? settings.endDateParam.trim() || DEFAULT_END_DATE_PARAM : undefined,
  };
};

const withoutUndefined = <T extends object>(value: T): T =>
  Object.fromEntries(Object.entries(value).filter(([, v]) => v !== undefined)) as T;

/** The job payload for the selected job type. Column styles only shape emailed reports. */
export const toPayload = (values: ScheduledJobFormValues): ScheduledJobQueryPayload | ScheduledJobEmailPayload => {
  const isEmailJob = values.jobType === JOB_TYPE_EMAIL_DYNAMIC_QUERY;
  const queryPayload: ScheduledJobQueryPayload = withoutUndefined({
    datasource_id: values.datasourceId,
    queries: values.queries.map(
      ({ queryId, overrides }): ScheduledJobQuerySpec =>
        withoutUndefined({
          query_id: queryId,
          datasource_id: overrides.datasourceId.trim() || undefined,
          ...settingsToPayload(overrides, isEmailJob),
        })
    ),
    ...settingsToPayload(values.defaults, isEmailJob),
  });
  if (!isEmailJob) return queryPayload;
  return withoutUndefined({
    ...queryPayload,
    recipient_user_ids: values.recipientUserIds,
    email_connection_id: values.emailConnectionId,
    subject: values.subject.trim() || undefined,
    email_content: values.emailContent.trim() || undefined,
  });
};
