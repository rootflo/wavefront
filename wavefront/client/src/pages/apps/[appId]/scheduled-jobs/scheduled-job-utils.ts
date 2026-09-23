import {
  DATE_RANGE,
  DEFAULT_END_DATE_PARAM,
  DEFAULT_START_DATE_PARAM,
  isPayloadDateRange,
} from '@app/constants/scheduled-job';
import {
  ColumnStyleConfig,
  DateRangeOption,
  QuerySpecFormOverrides,
  ScheduledJob,
  ScheduledJobEmailPayload,
  ScheduledJobQuerySpec,
} from '@app/types/scheduled-job';
import { IUser } from '@app/types/user';

export const normalizeUserId = (id: string) => id.trim().toLowerCase();

export const formatUserLabel = (user: IUser) => `${user.first_name} ${user.last_name} (${user.email})`;

export const extractRecipientUserIdsFromPayload = (payload: Record<string, unknown>): string[] => {
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

export const resolveUsersFromRecipientIds = (ids: string[], users: IUser[]): IUser[] => {
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

export const getQueryIdsFromPayload = (payload: Record<string, unknown>): string[] => {
  const queries = payload.queries;
  if (!Array.isArray(queries)) return [];

  const ids: string[] = [];
  for (const item of queries) {
    if (item && typeof item === 'object' && 'query_id' in item) {
      const queryId = String((item as { query_id: unknown }).query_id).trim();
      if (queryId) ids.push(queryId);
    }
  }
  return ids;
};

export const getDatasourceIdFromPayload = (payload: Record<string, unknown>): string => {
  if (typeof payload.datasource_id === 'string' && payload.datasource_id.trim()) {
    return payload.datasource_id.trim();
  }
  return '';
};

export const getEmailConnectionIdFromPayload = (payload: Record<string, unknown>): string => {
  if (typeof payload.email_connection_id === 'string' && payload.email_connection_id.trim()) {
    return payload.email_connection_id.trim();
  }
  return '';
};

const parseOptionalNonNegativeInt = (value: string | undefined): number | undefined => {
  if (value === undefined || !value.trim()) return undefined;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) return undefined;
  return parsed;
};

const buildQuerySpecFromOverrides = (
  queryId: string,
  overrides: QuerySpecFormOverrides | undefined,
  parsedParams?: Record<string, unknown>,
  parsedColumnStyles?: ColumnStyleConfig[]
): ScheduledJobQuerySpec => {
  const spec: ScheduledJobQuerySpec = { query_id: queryId };
  if (!overrides) return spec;

  if (overrides.datasource_id?.trim()) {
    spec.datasource_id = overrides.datasource_id.trim();
  }
  if (overrides.filter?.trim()) {
    spec.filter = overrides.filter.trim();
  }
  const offset = parseOptionalNonNegativeInt(overrides.offset);
  if (offset !== undefined) {
    spec.offset = offset;
  }
  const limit = parseOptionalNonNegativeInt(overrides.limit);
  if (limit !== undefined) {
    spec.limit = limit;
  }
  if (parsedParams) {
    spec.params = parsedParams;
  }
  if (parsedColumnStyles) {
    spec.column_styles = parsedColumnStyles;
  }
  if (overrides.date_range && overrides.date_range !== DATE_RANGE.NONE) {
    spec.date_range = overrides.date_range;
    spec.start_date_param = overrides.start_date_param?.trim() || DEFAULT_START_DATE_PARAM;
    spec.end_date_param = overrides.end_date_param?.trim() || DEFAULT_END_DATE_PARAM;
  }
  return spec;
};

export const buildEmailPayload = (args: {
  datasourceId: string;
  queryIds: string[];
  queryOverrides?: Record<string, QuerySpecFormOverrides>;
  queryOverrideParams?: Record<string, Record<string, unknown> | undefined>;
  queryOverrideColumnStyles?: Record<string, ColumnStyleConfig[] | undefined>;
  recipientUserIds: string[];
  emailConnectionId: string;
  subject?: string;
  emailContent?: string;
  columnStyles?: ColumnStyleConfig[];
  dateRange?: ScheduledJobEmailPayload['date_range'];
  startDateParam?: string;
  endDateParam?: string;
  params?: Record<string, unknown>;
  filter?: string;
  offset?: number;
  limit?: number;
}): ScheduledJobEmailPayload => ({
  datasource_id: args.datasourceId,
  queries: args.queryIds.map((queryId) =>
    buildQuerySpecFromOverrides(
      queryId,
      args.queryOverrides?.[queryId],
      args.queryOverrideParams?.[queryId],
      args.queryOverrideColumnStyles?.[queryId]
    )
  ),
  recipient_user_ids: args.recipientUserIds,
  email_connection_id: args.emailConnectionId,
  subject: args.subject,
  email_content: args.emailContent,
  column_styles: args.columnStyles,
  date_range: args.dateRange,
  start_date_param: args.startDateParam,
  end_date_param: args.endDateParam,
  params: args.params,
  filter: args.filter,
  offset: args.offset,
  limit: args.limit,
});

export const extractQueryOverridesFromPayload = (
  payload: Record<string, unknown>
): { queryIds: string[]; overrides: Record<string, QuerySpecFormOverrides> } => {
  const queries = payload.queries;
  const overrides: Record<string, QuerySpecFormOverrides> = {};
  const queryIds: string[] = [];

  if (!Array.isArray(queries)) {
    return { queryIds, overrides };
  }

  for (const item of queries) {
    if (!item || typeof item !== 'object') continue;
    const raw = item as Record<string, unknown>;
    const queryId = typeof raw.query_id === 'string' ? raw.query_id.trim() : '';
    if (!queryId) continue;
    queryIds.push(queryId);

    const next: QuerySpecFormOverrides = {};
    if (typeof raw.datasource_id === 'string' && raw.datasource_id.trim()) {
      next.datasource_id = raw.datasource_id.trim();
    }
    if (typeof raw.filter === 'string') {
      next.filter = raw.filter;
    }
    if (typeof raw.offset === 'number' && Number.isInteger(raw.offset) && raw.offset >= 0) {
      next.offset = String(raw.offset);
    }
    if (typeof raw.limit === 'number' && Number.isInteger(raw.limit) && raw.limit >= 0) {
      next.limit = String(raw.limit);
    }
    if (raw.params && typeof raw.params === 'object' && !Array.isArray(raw.params)) {
      next.paramsJson = JSON.stringify(raw.params, null, 2);
    }
    if (Array.isArray(raw.column_styles) && raw.column_styles.length > 0) {
      next.columnStylesJson = JSON.stringify(raw.column_styles, null, 2);
    }
    if (isPayloadDateRange(raw.date_range)) {
      next.date_range = raw.date_range;
    } else {
      next.date_range = DATE_RANGE.NONE;
    }
    if (typeof raw.start_date_param === 'string') {
      next.start_date_param = raw.start_date_param;
    }
    if (typeof raw.end_date_param === 'string') {
      next.end_date_param = raw.end_date_param;
    }

    if (Object.keys(next).length > 0) {
      overrides[queryId] = next;
    }
  }

  return { queryIds, overrides };
};

export const toDateRangeOption = (value: unknown): DateRangeOption =>
  isPayloadDateRange(value) ? value : DATE_RANGE.NONE;

export const formatJobQueriesLabel = (job: ScheduledJob): string => {
  const ids = getQueryIdsFromPayload(job.payload || {});
  if (ids.length === 0) return '—';
  if (ids.length <= 2) return ids.join(', ');
  return `${ids.slice(0, 2).join(', ')} +${ids.length - 2} more`;
};

export const formatDateTime = (value: string | null): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};
