import { IApiResponse } from '@app/lib/axios';
import {
  CreateSecretRequest,
  SecretData,
  SecretListData,
  SecretListResponse,
  SecretResponse,
  UpdateSecretRequest,
} from '@app/types/secret';
import { AxiosInstance } from 'axios';

/** Named secrets API services reference as `${secrets.NAME}` (admin only). */
export class SecretService {
  constructor(private http: AxiosInstance) {}

  async createSecret(data: CreateSecretRequest): Promise<SecretResponse> {
    const response: IApiResponse<SecretData> = await this.http.post(`/v1/:appId/floware/v1/secrets`, data);
    return response;
  }

  async listSecrets(): Promise<SecretListResponse> {
    const response: IApiResponse<SecretListData> = await this.http.get(`/v1/:appId/floware/v1/secrets`);
    return response;
  }

  async getSecret(secretId: string): Promise<SecretResponse> {
    const response: IApiResponse<SecretData> = await this.http.get(`/v1/:appId/floware/v1/secrets/${secretId}`);
    return response;
  }

  async updateSecret(secretId: string, data: UpdateSecretRequest): Promise<SecretResponse> {
    const response: IApiResponse<SecretData> = await this.http.put(`/v1/:appId/floware/v1/secrets/${secretId}`, data);
    return response;
  }

  async deleteSecret(secretId: string): Promise<SecretResponse> {
    const response: IApiResponse<SecretData> = await this.http.delete(`/v1/:appId/floware/v1/secrets/${secretId}`);
    return response;
  }
}
