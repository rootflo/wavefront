import {
  CreateScheduledJobRequest,
  CreateScheduledJobResponse,
  DeleteScheduledJobResponse,
  ListScheduledJobsResponse,
  UpdateScheduledJobResponse,
} from '@app/types/scheduled-job';
import { AxiosInstance } from 'axios';

export class ScheduledJobService {
  constructor(private http: AxiosInstance) {}

  async createScheduledJob(request: CreateScheduledJobRequest): Promise<CreateScheduledJobResponse> {
    return this.http.post(`/v1/:appId/floware/v1/scheduled-jobs`, request);
  }

  async listScheduledJobs(params: {
    limit?: number;
    query_id?: string;
    datasource_id?: string;
    job_type?: string;
    job_status?: string;
  }): Promise<ListScheduledJobsResponse> {
    return this.http.get(`/v1/:appId/floware/v1/scheduled-jobs`, { params });
  }

  async updateScheduledJob(
    jobId: string,
    payload: {
      cron_expr?: string;
      timezone?: string;
      payload?: Record<string, unknown>;
      max_retries?: number;
      status?: 'active' | 'paused' | 'running' | 'failed' | 'completed';
    }
  ): Promise<UpdateScheduledJobResponse> {
    return this.http.patch(`/v1/:appId/floware/v1/scheduled-jobs/${jobId}`, payload);
  }

  async deleteScheduledJob(jobId: string): Promise<DeleteScheduledJobResponse> {
    return this.http.delete(`/v1/:appId/floware/v1/scheduled-jobs/${jobId}`);
  }
}
