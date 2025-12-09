import { IApiResponse } from "@app/lib/axios";
import {
  CreateTtsConfigRequest,
  TtsConfig,
  TtsConfigData,
  TtsConfigDetailResponse,
  TtsConfigListData,
  TtsConfigListResponse,
  TtsConfigResponse,
  UpdateTtsConfigRequest,
} from "@app/types/tts-config";
import { AxiosInstance } from "axios";

export class TtsConfigService {
  constructor(private http: AxiosInstance) {}

  async createTtsConfig(
    data: CreateTtsConfigRequest
  ): Promise<TtsConfigResponse> {
    const response: IApiResponse<TtsConfigData> = await this.http.post(
      `/v1/:appId/floware/v1/tts-configs`,
      data
    );
    return response;
  }

  async getTtsConfig(configId: string): Promise<TtsConfigDetailResponse> {
    const response: IApiResponse<TtsConfig> = await this.http.get(
      `/v1/:appId/floware/v1/tts-configs/${configId}`
    );
    return response;
  }

  async updateTtsConfig(
    configId: string,
    data: UpdateTtsConfigRequest
  ): Promise<TtsConfigResponse> {
    const response: IApiResponse<TtsConfigData> = await this.http.put(
      `/v1/:appId/floware/v1/tts-configs/${configId}`,
      data
    );
    return response;
  }

  async deleteTtsConfig(configId: string): Promise<TtsConfigResponse> {
    const response: IApiResponse<TtsConfigData> = await this.http.delete(
      `/v1/:appId/floware/v1/tts-configs/${configId}`
    );
    return response;
  }

  async listAllTtsConfigs(): Promise<TtsConfigListResponse> {
    const response: IApiResponse<TtsConfigListData> = await this.http.get(
      `/v1/:appId/floware/v1/tts-configs`
    );
    return response;
  }
}
