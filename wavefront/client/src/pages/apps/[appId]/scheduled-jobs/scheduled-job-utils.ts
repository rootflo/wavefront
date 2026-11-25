import { DATE_RANGE, isPayloadDateRange } from '@app/constants/scheduled-job';
import { DateRangeOption, ScheduledJob } from '@app/types/scheduled-job';
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
