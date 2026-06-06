import { ScheduledJob, ScheduledJobEmailPayload } from '@app/types/scheduled-job';
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

export const buildEmailPayload = (args: {
  datasourceId: string;
  queryIds: string[];
  recipientUserIds: string[];
  subject?: string;
  emailContent?: string;
  columnStyles?: ScheduledJobEmailPayload['column_styles'];
  dateRange?: ScheduledJobEmailPayload['date_range'];
  startDateParam?: string;
  endDateParam?: string;
  params?: Record<string, unknown>;
}): ScheduledJobEmailPayload => ({
  datasource_id: args.datasourceId,
  queries: args.queryIds.map((query_id) => ({ query_id })),
  recipient_user_ids: args.recipientUserIds,
  subject: args.subject,
  email_content: args.emailContent,
  column_styles: args.columnStyles,
  date_range: args.dateRange,
  start_date_param: args.startDateParam,
  end_date_param: args.endDateParam,
  params: args.params,
});

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
