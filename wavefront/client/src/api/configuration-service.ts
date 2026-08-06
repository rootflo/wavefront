import { IApiResponse } from '@app/lib/axios';
import {
  ConfigurationListData,
  ConfigurationListItem,
  ConfigurationListResponse,
  ConfigurationResponse,
  ConfigurationValue,
  ConfigurationValueResponse,
  CreateConfigurationRequest,
  UpsertConfigurationRequest,
} from '@app/types/configuration';
import { AxiosInstance } from 'axios';

/**
 * Configurations are addressed by (namespace, key), so every path segment is
 * encoded — a key may legitimately contain characters that would otherwise
 * change the route.
 */
export class ConfigurationService {
  constructor(private http: AxiosInstance) {}

  async createConfiguration(data: CreateConfigurationRequest): Promise<ConfigurationResponse> {
    const response: IApiResponse<ConfigurationListItem> = await this.http.post(
      `/v1/:appId/floware/v1/configurations`,
      data
    );
    return response;
  }

  /** Returns the configuration document itself, not a wrapper around it. */
  async getConfiguration(namespace: string, key: string): Promise<ConfigurationValueResponse> {
    const response: IApiResponse<ConfigurationValue> = await this.http.get(
      `/v1/:appId/floware/v1/configurations/${encodeURIComponent(namespace)}/${encodeURIComponent(key)}`
    );
    return response;
  }

  /** Replaces the value wholesale — it is not merged into the stored document. */
  async upsertConfiguration(
    namespace: string,
    key: string,
    data: UpsertConfigurationRequest
  ): Promise<ConfigurationResponse> {
    const response: IApiResponse<ConfigurationListItem> = await this.http.put(
      `/v1/:appId/floware/v1/configurations/${encodeURIComponent(namespace)}/${encodeURIComponent(key)}`,
      data
    );
    return response;
  }

  async deleteConfiguration(namespace: string, key: string): Promise<ConfigurationResponse> {
    const response: IApiResponse<ConfigurationListItem> = await this.http.delete(
      `/v1/:appId/floware/v1/configurations/${encodeURIComponent(namespace)}/${encodeURIComponent(key)}`
    );
    return response;
  }

  async listConfigurations(namespace?: string): Promise<ConfigurationListResponse> {
    const response: IApiResponse<ConfigurationListData> = await this.http.get(`/v1/:appId/floware/v1/configurations`, {
      params: namespace ? { namespace } : undefined,
    });
    return response;
  }
}
