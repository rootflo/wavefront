import type { DateRangeOption, FormTab, PayloadDateRange } from '@app/types/scheduled-job';

export const DEFAULT_CRON_EXPR = '0 9 * * *';
export const DEFAULT_TIMEZONE = 'Asia/Kolkata';
export const DEFAULT_MAX_RETRIES = '3';
export const DEFAULT_START_DATE_PARAM = 'start_date';
export const DEFAULT_END_DATE_PARAM = 'end_date';
export const MAX_RETRIES_LIMIT = 10;
export const JOB_TYPE_EMAIL_DYNAMIC_QUERY = 'email_dynamic_query' as const;

export const FORM_TAB = {
  SCHEDULE: 'schedule',
  EMAIL: 'email',
} as const satisfies Record<string, FormTab>;

export const DATE_RANGE = {
  NONE: 'none',
  LAST_HOUR: 'last_hour',
  LAST_DAY: 'last_day',
  T_2: 't_2',
  LAST_7_DAYS: 'last_7_days',
  LAST_30_DAYS: 'last_30_days',
} as const satisfies Record<string, DateRangeOption>;

export const PAYLOAD_DATE_RANGES = [
  DATE_RANGE.LAST_HOUR,
  DATE_RANGE.LAST_DAY,
  DATE_RANGE.T_2,
  DATE_RANGE.LAST_7_DAYS,
  DATE_RANGE.LAST_30_DAYS,
] as const satisfies readonly PayloadDateRange[];

export const COLUMN_STYLES_PLACEHOLDER = `[
  {
    "column": "Total calls attempted",
    "rules": [
      { "op": "eq", "value": 0, "fill": "light_red" },
      { "op": "lt", "value": 160, "fill": "light_yellow" },
      { "op": "gte", "value": 225, "fill": "dark_green" }
    ]
  }
]`;

export const QUERY_PARAMS_PLACEHOLDER = `{"${DEFAULT_START_DATE_PARAM}":"2026-03-01","${DEFAULT_END_DATE_PARAM}":"2026-03-31"}`;
export const EMAIL_CONTENT_PLACEHOLDER = `Here is your result\n{my_query_id}\n\nSee more\n{another_query_id}`;

export const isFormTab = (value: string): value is FormTab => value === FORM_TAB.SCHEDULE || value === FORM_TAB.EMAIL;

export const isPayloadDateRange = (value: unknown): value is PayloadDateRange =>
  PAYLOAD_DATE_RANGES.some((range) => range === value);
