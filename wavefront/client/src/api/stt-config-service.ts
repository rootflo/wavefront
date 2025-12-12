import { IApiResponse } from "@app/lib/axios";
import {
  CreateSttConfigRequest,
  SttConfig,
  SttConfigData,
  SttConfigDetailResponse,
  SttConfigListData,
  SttConfigListResponse,
  SttConfigResponse,
  UpdateSttConfigRequest,
} from "@app/types/stt-config";
import { AxiosInstance } from "axios";

export class SttConfigService {
  constructor(private http: AxiosInstance) {}

  async createSttConfig(
    data: CreateSttConfigRequest
  ): Promise<SttConfigResponse> {
    const response: IApiResponse<SttConfigData> = await this.http.post(
      `/v1/:appId/floware/v1/stt-configs`,
      data
    );
    return response;
  }

  async getSttConfig(configId: string): Promise<SttConfigDetailResponse> {
    const response: IApiResponse<SttConfig> = await this.http.get(
      `/v1/:appId/floware/v1/stt-configs/${configId}`
    );
    return response;
  }

  async updateSttConfig(
    configId: string,
    data: UpdateSttConfigRequest
  ): Promise<SttConfigResponse> {
    const response: IApiResponse<SttConfigData> = await this.http.put(
      `/v1/:appId/floware/v1/stt-configs/${configId}`,
      data
    );
    return response;
  }

  async deleteSttConfig(configId: string): Promise<SttConfigResponse> {
    const response: IApiResponse<SttConfigData> = await this.http.delete(
      `/v1/:appId/floware/v1/stt-configs/${configId}`
    );
    return response;
  }

  async listAllSttConfigs(): Promise<SttConfigListResponse> {
    const response: IApiResponse<SttConfigListData> = await this.http.get(
      `/v1/:appId/floware/v1/stt-configs`
    );
    return response;
  }
}
