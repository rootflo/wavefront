import { DATE_RANGE } from '@app/constants/scheduled-job';
import { ColumnStyleConfig, DateRangeOption, QuerySpecFormOverrides } from '@app/types/scheduled-job';
import { IUser } from '@app/types/user';

// Defaults and input parsing for the scheduled job form

export const getUserId = (user: IUser) => user.id;
export const getUserSearchValue = (user: IUser) => `${user.first_name} ${user.last_name} ${user.email}`;
export const selectedUsersCountLabel = (count: number) => `${count} users selected`;

export type QueryConfigEntry = {
  key: string;
  queryId: string;
  overrides: QuerySpecFormOverrides;
};

export const createQueryConfigKey = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `query-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

export const createEmptyOverrides = (): QuerySpecFormOverrides => ({ date_range: DATE_RANGE.NONE });

export const createEmptyQueryConfig = (): QueryConfigEntry => ({
  key: createQueryConfigKey(),
  queryId: '',
  overrides: createEmptyOverrides(),
});

export const DATE_RANGE_OPTIONS: { value: DateRangeOption; label: string }[] = [
  { value: DATE_RANGE.NONE, label: 'None' },
  { value: DATE_RANGE.LAST_HOUR, label: 'Last hour' },
  { value: DATE_RANGE.LAST_DAY, label: 'Last day' },
  { value: DATE_RANGE.T_2, label: 'T-2 (2 days ago)' },
  { value: DATE_RANGE.LAST_7_DAYS, label: 'Last 7 days' },
  { value: DATE_RANGE.LAST_30_DAYS, label: 'Last 30 days' },
];

export const isDateRangeOption = (value: string): value is DateRangeOption =>
  DATE_RANGE_OPTIONS.some((option) => option.value === value);

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
