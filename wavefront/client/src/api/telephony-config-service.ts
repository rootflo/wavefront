import { IApiResponse } from "@app/lib/axios";
import {
  CreateTelephonyConfigRequest,
  TelephonyConfig,
  TelephonyConfigData,
  TelephonyConfigDetailResponse,
  TelephonyConfigListData,
  TelephonyConfigListResponse,
  TelephonyConfigResponse,
  UpdateTelephonyConfigRequest,
} from "@app/types/telephony-config";
import { AxiosInstance } from "axios";

export class TelephonyConfigService {
  constructor(private http: AxiosInstance) {}

  async createTelephonyConfig(
    data: CreateTelephonyConfigRequest
  ): Promise<TelephonyConfigResponse> {
    const response: IApiResponse<TelephonyConfigData> = await this.http.post(
      `/v1/:appId/floware/v1/telephony-configs`,
      data
    );
    return response;
  }

  async getTelephonyConfig(
    configId: string
  ): Promise<TelephonyConfigDetailResponse> {
    const response: IApiResponse<TelephonyConfig> = await this.http.get(
      `/v1/:appId/floware/v1/telephony-configs/${configId}`
    );
    return response;
  }

  async updateTelephonyConfig(
    configId: string,
    data: UpdateTelephonyConfigRequest
  ): Promise<TelephonyConfigResponse> {
    const response: IApiResponse<TelephonyConfigData> = await this.http.put(
      `/v1/:appId/floware/v1/telephony-configs/${configId}`,
      data
    );
    return response;
  }

  async deleteTelephonyConfig(
    configId: string
  ): Promise<TelephonyConfigResponse> {
    const response: IApiResponse<TelephonyConfigData> = await this.http.delete(
      `/v1/:appId/floware/v1/telephony-configs/${configId}`
    );
    return response;
  }

  async listAllTelephonyConfigs(): Promise<TelephonyConfigListResponse> {
    const response: IApiResponse<TelephonyConfigListData> = await this.http.get(
      `/v1/:appId/floware/v1/telephony-configs`
    );
    return response;
  }
}
