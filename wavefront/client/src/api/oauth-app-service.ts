import { IApiResponse } from '@app/lib/axios';
import { EmailProviderType } from '@app/types/email';
import {
  CreateOAuthAppRequest,
  OAuthAppData,
  OAuthAppDetailData,
  OAuthAppDetailResponse,
  OAuthAppListData,
  OAuthAppListResponse,
  OAuthAppMessageData,
  OAuthAppMessageResponse,
  OAuthAppResponse,
  UpdateOAuthAppRequest,
} from '@app/types/oauth-app';
import { AxiosInstance } from 'axios';

/** Platform OAuth client credentials (admin only). */
export class OAuthAppService {
  constructor(private http: AxiosInstance) {}

  async createOAuthApp(data: CreateOAuthAppRequest): Promise<OAuthAppResponse> {
    const response: IApiResponse<OAuthAppData> = await this.http.post(`/v1/:appId/floware/v1/oauth-apps`, data);
    return response;
  }

  async getAllOAuthApps(provider?: EmailProviderType): Promise<OAuthAppListResponse> {
    const response: IApiResponse<OAuthAppListData> = await this.http.get(`/v1/:appId/floware/v1/oauth-apps`, {
      params: provider ? { provider } : undefined,
    });
    return response;
  }

  async getOAuthApp(appId: string): Promise<OAuthAppDetailResponse> {
    const response: IApiResponse<OAuthAppDetailData> = await this.http.get(`/v1/:appId/floware/v1/oauth-apps/${appId}`);
    return response;
  }

  async updateOAuthApp(appId: string, data: UpdateOAuthAppRequest): Promise<OAuthAppResponse> {
    const response: IApiResponse<OAuthAppData> = await this.http.patch(
      `/v1/:appId/floware/v1/oauth-apps/${appId}`,
      data
    );
    return response;
  }

  async enableOAuthApp(appId: string): Promise<OAuthAppResponse> {
    const response: IApiResponse<OAuthAppData> = await this.http.post(
      `/v1/:appId/floware/v1/oauth-apps/${appId}/enable`
    );
    return response;
  }

  async disableOAuthApp(appId: string): Promise<OAuthAppResponse> {
    const response: IApiResponse<OAuthAppData> = await this.http.post(
      `/v1/:appId/floware/v1/oauth-apps/${appId}/disable`
    );
    return response;
  }

  async deleteOAuthApp(appId: string): Promise<OAuthAppMessageResponse> {
    const response: IApiResponse<OAuthAppMessageData> = await this.http.delete(
      `/v1/:appId/floware/v1/oauth-apps/${appId}`
    );
    return response;
  }
}
