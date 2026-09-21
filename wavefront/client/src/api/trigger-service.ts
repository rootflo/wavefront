import {
  CreateTriggerRequest,
  CreateTriggerResponse,
  ListTriggersResponse,
  TriggerDetailResponse,
} from '@app/types/trigger';
import { AxiosInstance } from 'axios';

export class TriggerService {
  constructor(private http: AxiosInstance) {}

  async createTrigger(request: CreateTriggerRequest): Promise<CreateTriggerResponse> {
    return this.http.post(`/v1/:appId/floware/v1/triggers`, request);
  }

  async listTriggers(params?: {
    provider?: string;
    namespace?: string;
    status?: string;
    limit?: number;
  }): Promise<ListTriggersResponse> {
    return this.http.get(`/v1/:appId/floware/v1/triggers`, { params });
  }

  async getTrigger(triggerId: string): Promise<TriggerDetailResponse> {
    return this.http.get(`/v1/:appId/floware/v1/triggers/${triggerId}`);
  }

  async pauseTrigger(triggerId: string): Promise<TriggerDetailResponse> {
    return this.http.post(`/v1/:appId/floware/v1/triggers/${triggerId}/pause`);
  }

  async resumeTrigger(triggerId: string): Promise<TriggerDetailResponse> {
    return this.http.post(`/v1/:appId/floware/v1/triggers/${triggerId}/resume`);
  }

  async retryTrigger(triggerId: string): Promise<TriggerDetailResponse> {
    return this.http.post(`/v1/:appId/floware/v1/triggers/${triggerId}/retry`);
  }

  async deleteTrigger(triggerId: string): Promise<void> {
    await this.http.delete(`/v1/:appId/floware/v1/triggers/${triggerId}`);
  }
}
