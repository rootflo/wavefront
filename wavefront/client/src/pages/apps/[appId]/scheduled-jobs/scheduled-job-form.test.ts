import { describe, expect, it } from 'vitest';
import { ScheduledJob } from '@app/types/scheduled-job';
import {
  parseJsonArray,
  parseJsonObject,
  parseOptionalNonNegativeInt,
  scheduledJobFormSchema,
  toFormValues,
  toPayload,
} from './scheduled-job-form';

describe('scheduled job form parsing', () => {
  it('treats blank optional fields as unset', () => {
    expect(parseOptionalNonNegativeInt('  ', 'Offset')).toEqual({ ok: true, value: undefined });
    expect(parseJsonObject('', 'Params')).toEqual({ ok: true, value: undefined });
    expect(parseJsonArray('', 'Styles')).toEqual({ ok: true, value: undefined });
  });

  it('accepts whole numbers from zero up, and names the field when rejecting others', () => {
    expect(parseOptionalNonNegativeInt('0', 'Offset')).toEqual({ ok: true, value: 0 });
    expect(parseOptionalNonNegativeInt('25', 'Limit')).toEqual({ ok: true, value: 25 });
    expect(parseOptionalNonNegativeInt('-1', 'Offset')).toEqual({
      ok: false,
      error: 'Offset must be a non-negative integer',
    });
    expect(parseOptionalNonNegativeInt('2.5', 'Limit')).toMatchObject({ ok: false });
  });

  it('accepts only a JSON object for params', () => {
    expect(parseJsonObject('{"region": "eu"}', 'Params')).toEqual({ ok: true, value: { region: 'eu' } });
    expect(parseJsonObject('[1]', 'Params')).toEqual({ ok: false, error: 'Params must be a JSON object' });
    expect(parseJsonObject('null', 'Params')).toMatchObject({ ok: false });
    expect(parseJsonObject('{oops', 'Params')).toEqual({ ok: false, error: 'Params must be valid JSON (object)' });
  });

  it('accepts only a JSON array for column styles', () => {
    expect(parseJsonArray('[]', 'Styles')).toEqual({ ok: true, value: [] });
    expect(parseJsonArray('{}', 'Styles')).toEqual({ ok: false, error: 'Styles must be a JSON array' });
  });
});

const makeJob = (job_type: ScheduledJob['job_type'], payload: Record<string, unknown>): ScheduledJob => ({
  id: 'job-1',
  job_type,
  cron_expr: '*/30 * * * *',
  timezone: 'UTC',
  status: 'active',
  payload,
  next_run_at: null,
  last_run_at: null,
  last_error: null,
  retry_count: 0,
  max_retries: 3,
  created_at: null,
  updated_at: null,
});

const emailPayload = {
  datasource_id: 'ds-1',
  queries: [
    { query_id: 'sales' },
    {
      query_id: 'refunds',
      datasource_id: 'ds-2',
      filter: "status eq 'open'",
      limit: 10,
      params: { region: 'eu' },
      column_styles: [{ column: 'Total', rules: [{ op: 'eq', value: 0, fill: 'light_red' }] }],
      date_range: 'last_7_days',
      start_date_param: 'from',
      end_date_param: 'to',
    },
  ],
  recipient_user_ids: ['user-1'],
  email_connection_id: 'conn-1',
  subject: 'Daily',
  limit: 100,
  offset: 0,
};

describe('scheduled job form values', () => {
  it('round-trips an email job payload, per-query overrides included', () => {
    const values = toFormValues(makeJob('email_dynamic_query', emailPayload));
    expect(scheduledJobFormSchema.safeParse(values).success).toBe(true);
    expect(toPayload(values)).toEqual(emailPayload);
  });

  it('leaves email fields and column styles out of a scheduled query payload', () => {
    const values = toFormValues(makeJob('email_dynamic_query', emailPayload));
    const payload = toPayload({ ...values, jobType: 'scheduled_query' });
    expect(payload).not.toHaveProperty('recipient_user_ids');
    expect(payload).not.toHaveProperty('email_connection_id');
    expect(payload.queries[1]).not.toHaveProperty('column_styles');
  });

  it('requires recipients and a sender only for email jobs', () => {
    const values = { ...toFormValues(makeJob('email_dynamic_query', emailPayload)), recipientUserIds: [] };
    const emailResult = scheduledJobFormSchema.safeParse({ ...values, emailConnectionId: '' });
    expect(emailResult.success).toBe(false);
    expect(emailResult.error?.issues.map((issue) => issue.path.join('.'))).toEqual([
      'recipientUserIds',
      'emailConnectionId',
    ]);
    expect(
      scheduledJobFormSchema.safeParse({ ...values, jobType: 'scheduled_query', emailConnectionId: '' }).success
    ).toBe(true);
  });

  it('flags bad fields at their path, inside the queries array too', () => {
    const values = toFormValues(
      makeJob('scheduled_query', { datasource_id: 'ds-1', queries: [{ query_id: 'sales' }] })
    );
    const result = scheduledJobFormSchema.safeParse({
      ...values,
      maxRetries: '11',
      queries: [{ ...values.queries[0], overrides: { ...values.queries[0].overrides, limit: '-1' } }],
    });
    expect(result.error?.issues.map((issue) => [issue.path.join('.'), issue.message])).toEqual([
      ['maxRetries', 'Max retries must be an integer between 0 and 10'],
      ['queries.0.overrides.limit', 'Row limit must be a non-negative integer'],
    ]);
  });

  it('needs at least one query for a new job', () => {
    const result = scheduledJobFormSchema.safeParse({
      ...toFormValues(),
      datasourceId: 'ds-1',
      jobType: 'scheduled_query',
    });
    expect(result.error?.issues.map((issue) => issue.message)).toEqual(['Add at least one query']);
  });

  it('checks column styles only for email jobs, keeping them for a switch back', () => {
    const base = toFormValues(makeJob('email_dynamic_query', emailPayload));
    const values = {
      ...base,
      defaults: { ...base.defaults, columnStylesJson: '{}' },
      queries: [{ ...base.queries[0], overrides: { ...base.queries[0].overrides, columnStylesJson: '[oops' } }],
    };

    const emailResult = scheduledJobFormSchema.safeParse(values);
    expect(emailResult.error?.issues.map((issue) => [issue.path.join('.'), issue.message])).toEqual([
      ['defaults.columnStylesJson', 'Column styles must be a JSON array'],
      ['queries.0.overrides.columnStylesJson', 'Column styles must be valid JSON (array)'],
    ]);

    const queryOnly = scheduledJobFormSchema.safeParse({ ...values, jobType: 'scheduled_query' });
    expect(queryOnly.success).toBe(true);
    expect(queryOnly.data?.defaults.columnStylesJson).toBe('{}');
    expect(toPayload(queryOnly.data!)).not.toHaveProperty('column_styles');
  });
});
