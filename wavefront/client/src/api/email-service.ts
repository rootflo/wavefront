import { IApiResponse } from '@app/lib/axios';
import {
  AuthorizeEmailConnectionRequest,
  CreateEmailConnectionRequest,
  EmailConnectionAuthorizeData,
  EmailConnectionAuthorizeResponse,
  EmailConnectionData,
  EmailConnectionDetailData,
  EmailConnectionDetailResponse,
  EmailConnectionListData,
  EmailConnectionListResponse,
  EmailConnectionMessageData,
  EmailConnectionMessageResponse,
  EmailConnectionPrimaryData,
  EmailConnectionPrimaryResponse,
  EmailConnectionResponse,
  EmailConnectionStatus,
  EmailProviderType,
  SendEmailRequest,
} from '@app/types/email';
import { AxiosInstance } from 'axios';

/** Connected mailboxes. Listing is open to any authenticated user so that agent
 *  and scheduled job authors can pick a sender; mutations are admin only. */
export class EmailConnectionService {
  constructor(private http: AxiosInstance) {}

  async createEmailConnection(data: CreateEmailConnectionRequest): Promise<EmailConnectionResponse> {
    const response: IApiResponse<EmailConnectionData> = await this.http.post(
      `/v1/:appId/floware/v1/email-connections`,
      data
    );
    return response;
  }

  async getAllEmailConnections(params?: {
    provider?: EmailProviderType;
    status?: EmailConnectionStatus;
  }): Promise<EmailConnectionListResponse> {
    const response: IApiResponse<EmailConnectionListData> = await this.http.get(
      `/v1/:appId/floware/v1/email-connections`,
      { params }
    );
    return response;
  }

  async getEmailConnection(connectionId: string): Promise<EmailConnectionDetailResponse> {
    const response: IApiResponse<EmailConnectionDetailData> = await this.http.get(
      `/v1/:appId/floware/v1/email-connections/${connectionId}`
    );
    return response;
  }

  async authorizeEmailConnection(
    connectionId: string,
    data: AuthorizeEmailConnectionRequest
  ): Promise<EmailConnectionAuthorizeResponse> {
    const response: IApiResponse<EmailConnectionAuthorizeData> = await this.http.post(
      `/v1/:appId/floware/v1/email-connections/${connectionId}/authorize`,
      data
    );
    return response;
  }

  async setPrimaryEmailConnection(connectionId: string): Promise<EmailConnectionPrimaryResponse> {
    const response: IApiResponse<EmailConnectionPrimaryData> = await this.http.post(
      `/v1/:appId/floware/v1/email-connections/${connectionId}/set-primary`
    );
    return response;
  }

  async verifyEmailConnection(connectionId: string): Promise<EmailConnectionPrimaryResponse> {
    const response: IApiResponse<EmailConnectionPrimaryData> = await this.http.post(
      `/v1/:appId/floware/v1/email-connections/${connectionId}/verify`
    );
    return response;
  }

  async sendFromEmailConnection(connectionId: string, data: SendEmailRequest): Promise<EmailConnectionMessageResponse> {
    const response: IApiResponse<EmailConnectionMessageData> = await this.http.post(
      `/v1/:appId/floware/v1/email-connections/${connectionId}/send`,
      data
    );
    return response;
  }

  async deleteEmailConnection(connectionId: string): Promise<EmailConnectionMessageResponse> {
    const response: IApiResponse<EmailConnectionMessageData> = await this.http.delete(
      `/v1/:appId/floware/v1/email-connections/${connectionId}`
    );
    return response;
  }
}
