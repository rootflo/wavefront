import { IApiResponse } from "@app/lib/axios";
import {
  Authenticator,
  AuthenticatorData,
  AuthenticatorDetailResponse,
  AuthenticatorEnableDisableData,
  AuthenticatorEnableDisableResponse,
  AuthenticatorListData,
  AuthenticatorListResponse,
  AuthenticatorResponse,
  CreateAuthenticatorRequest,
  UpdateAuthenticatorRequest,
} from "@app/types/authenticator";
import { AxiosInstance } from "axios";

export class AuthenticatorService {
  constructor(private http: AxiosInstance) {}

  async createAuthenticator(
    data: CreateAuthenticatorRequest
  ): Promise<AuthenticatorResponse> {
    const response: IApiResponse<AuthenticatorData> = await this.http.post(
      `/v1/:appId/floware/v1/authenticators`,
      data
    );
    return response;
  }

  async getAuthenticator(authId: string): Promise<AuthenticatorDetailResponse> {
    const response: IApiResponse<Authenticator> = await this.http.get(
      `/v1/:appId/floware/v1/authenticators/${authId}`
    );
    return response;
  }

  async getAllAuthenticators(): Promise<AuthenticatorListResponse> {
    const response: IApiResponse<AuthenticatorListData> = await this.http.get(
      `/v1/:appId/floware/v1/authenticators`
    );
    return response;
  }

  async updateAuthenticator(
    authId: string,
    data: UpdateAuthenticatorRequest
  ): Promise<AuthenticatorResponse> {
    const response: IApiResponse<AuthenticatorData> = await this.http.put(
      `/v1/:appId/floware/v1/authenticators/${authId}`,
      data
    );
    return response;
  }

  async deleteAuthenticator(authId: string): Promise<AuthenticatorResponse> {
    const response: IApiResponse<AuthenticatorData> = await this.http.delete(
      `/v1/:appId/floware/v1/authenticators/${authId}`
    );
    return response;
  }

  async enableAuthenticator(
    authId: string
  ): Promise<AuthenticatorEnableDisableResponse> {
    const response: IApiResponse<AuthenticatorEnableDisableData> =
      await this.http.post(
        `/v1/:appId/floware/v1/authenticators/${authId}/enable`
      );
    return response;
  }

  async disableAuthenticator(
    authId: string
  ): Promise<AuthenticatorEnableDisableResponse> {
    const response: IApiResponse<AuthenticatorEnableDisableData> =
      await this.http.post(
        `/v1/:appId/floware/v1/authenticators/${authId}/disable`
      );
    return response;
  }
}
