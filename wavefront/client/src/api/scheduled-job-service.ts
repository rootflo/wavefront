import {
  CreateScheduledJobRequest,
  CreateScheduledJobResponse,
  DeleteScheduledJobResponse,
  ListScheduledJobsResponse,
  UpdateScheduledJobRequest,
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
    offset?: number;
    query_id?: string;
    datasource_id?: string;
    job_type?: string;
    job_status?: string;
  }): Promise<ListScheduledJobsResponse> {
    return this.http.get(`/v1/:appId/floware/v1/scheduled-jobs`, { params });
  }

  async updateScheduledJob(jobId: string, request: UpdateScheduledJobRequest): Promise<UpdateScheduledJobResponse> {
    return this.http.patch(`/v1/:appId/floware/v1/scheduled-jobs/${jobId}`, request);
  }

  async deleteScheduledJob(jobId: string): Promise<DeleteScheduledJobResponse> {
    return this.http.delete(`/v1/:appId/floware/v1/scheduled-jobs/${jobId}`);
  }

  async pauseScheduledJob(jobId: string): Promise<UpdateScheduledJobResponse> {
    return this.http.post(`/v1/:appId/floware/v1/scheduled-jobs/${jobId}/pause`);
  }

  async resumeScheduledJob(jobId: string): Promise<UpdateScheduledJobResponse> {
    return this.http.post(`/v1/:appId/floware/v1/scheduled-jobs/${jobId}/resume`);
  }
}
