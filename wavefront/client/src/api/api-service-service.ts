import { IApiResponse } from '@app/lib/axios';
import { ApiServiceData, ApiServiceListData, ApiServiceListResponse, ApiServiceResponse } from '@app/types/api-service';
import { AxiosInstance } from 'axios';

export class ApiServiceService {
  constructor(private http: AxiosInstance) {}

  async createApiService(yamlContent: string): Promise<ApiServiceResponse> {
    const response: IApiResponse<ApiServiceData> = await this.http.post(
      `/v1/:appId/floware/v1/api-services`,
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
      }
    );
    return response;
  }

  async getApiService(id: string): Promise<ApiServiceResponse> {
    const response: IApiResponse<ApiServiceData> = await this.http.get(`/v1/:appId/floware/v1/api-services/${id}`);
    return response;
  }

  async updateApiService(id: string, yamlContent: string): Promise<ApiServiceResponse> {
    const response: IApiResponse<ApiServiceData> = await this.http.put(
      `/v1/:appId/floware/v1/api-services/${id}`,
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
      }
    );
    return response;
  }

  async deleteApiService(id: string): Promise<ApiServiceResponse> {
    const response: IApiResponse<ApiServiceData> = await this.http.delete(`/v1/:appId/floware/v1/api-services/${id}`);
    return response;
  }

  async listApiServices(): Promise<ApiServiceListResponse> {
    const response: IApiResponse<ApiServiceListData> = await this.http.get(`/v1/:appId/floware/v1/api-services`);
    return response;
  }
}
