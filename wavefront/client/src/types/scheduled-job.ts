import { IApiResponse } from '@app/lib/axios';

export interface ScheduledJob {
  id: string;
  job_type: string;
  cron_expr: string;
  timezone: string;
  status: string;
  payload: Record<string, unknown>;
  next_run_at: string | null;
  last_run_at: string | null;
  last_error: string | null;
  retry_count: number;
  max_retries: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ScheduledJobResponseData {
  job: ScheduledJob;
}

export interface ScheduledJobListResponseData {
  jobs: ScheduledJob[];
}

export interface CreateScheduledJobRequest {
  job_type: 'email_dynamic_query';
  cron_expr: string;
  timezone: string;
  max_retries: number;
  payload: {
    datasource_id: string;
    query_id: string;
    recipients: string[];
    subject?: string;
    date_range?: 'last_day' | 'last_hour' | 'last_7_days' | 'last_30_days';
    start_date_param?: string;
    end_date_param?: string;
    offset?: number;
    limit?: number;
    params?: Record<string, unknown>;
  };
}

export type CreateScheduledJobResponse = IApiResponse<ScheduledJobResponseData>;
export type ListScheduledJobsResponse = IApiResponse<ScheduledJobListResponseData>;
export type UpdateScheduledJobResponse = IApiResponse<ScheduledJobResponseData>;
export type DeleteScheduledJobResponse = IApiResponse<{ message: string }>;
