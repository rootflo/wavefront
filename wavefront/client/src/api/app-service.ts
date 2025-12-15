import { IApiResponse } from '@app/lib/axios';
import {
  AppData,
  AppResponse,
  AppsData,
  AppStatusData,
  AppStatusResponse,
  CreateAppRequest,
  DeleteAppData,
  DeleteAppResponse,
  UpdateAppRequest,
} from '@app/types/app';
import { AxiosInstance } from 'axios';

export class AppService {
  constructor(private http: AxiosInstance) {}

  async getAllApps(): Promise<IApiResponse<AppsData>> {
    return this.http.get('/v1/apps');
  }

  async getAppById(appId: string): Promise<AppResponse> {
    const response: IApiResponse<AppData> = await this.http.get(`/v1/apps/${appId}`);
    return response;
  }

  async createApp(appData: CreateAppRequest): Promise<AppResponse> {
    const response: IApiResponse<AppData> = await this.http.post('/v1/apps', appData);
    return response;
  }

  async updateApp(appId: string, appData: UpdateAppRequest): Promise<AppResponse> {
    const response: IApiResponse<AppData> = await this.http.patch(`/v1/apps/${appId}`, appData);
    return response;
  }

  async deleteApp(appId: string, deleteDeployment: boolean): Promise<DeleteAppResponse> {
    const response: IApiResponse<DeleteAppData> = await this.http.delete(`/v1/apps/${appId}`, {
      params: {
        delete_deployment: deleteDeployment,
      },
    });
    return response;
  }

  async getAppStatus(appId: string): Promise<AppStatusResponse> {
    const response: IApiResponse<AppStatusData> = await this.http.get(`/v1/apps/${appId}/status`);
    return response;
  }
}
