import { IApiResponse } from "@app/lib/axios";
import {
  AllYamlsResponse,
  Datasource,
  DatasourceData,
  DatasourceResourcesData,
  DatasourceResourcesResponse,
  DatasourceResponse,
  DeleteYamlResponse,
  ExecuteYamlResponse,
  ReadYamlResponse,
  TestDatasourceData,
  TestDatasourceResponse,
  YamlResponse,
} from "@app/types/datasource";
import { AxiosInstance } from "axios";

export class DatasourcesService {
  constructor(private http: AxiosInstance) {}

  async createDatasource(
    name: string,
    type: string,
    config: Record<string, any>,
    description?: string
  ): Promise<DatasourceResponse> {
    const response: IApiResponse<DatasourceData> = await this.http.post(
      `/v1/:appId/floware/v1/datasources`,
      {
        name,
        type,
        config: JSON.stringify(config),
        description,
      }
    );
    return response;
  }

  async getDatasource(datasourceId: string): Promise<DatasourceResponse> {
    const response: IApiResponse<DatasourceData> = await this.http.get(
      `/v1/:appId/floware/v1/datasources/${datasourceId}`
    );
    return response;
  }

  async updateDatasource(
    datasourceId: string,
    name: string,
    type: string,
    config: Record<string, any>,
    description?: string
  ): Promise<DatasourceResponse> {
    const response: IApiResponse<DatasourceData> = await this.http.patch(
      `/v1/:appId/floware/v1/datasources/${datasourceId}`,
      {
        name,
        type,
        config: JSON.stringify(config),
        description,
      }
    );
    return response;
  }

  async deleteDatasource(datasourceId: string): Promise<DatasourceResponse> {
    const response: IApiResponse<DatasourceData> = await this.http.delete(
      `/v1/:appId/floware/v1/datasources/${datasourceId}`
    );
    return response;
  }

  async testDatasource(datasourceId: string): Promise<TestDatasourceResponse> {
    const response: IApiResponse<TestDatasourceData> = await this.http.post(
      `/v1/:appId/floware/v1/datasources/${datasourceId}/test-connection`
    );
    return response;
  }

  async getAllDatasources(): Promise<
    IApiResponse<{ datasources: Datasource[] }>
  > {
    return this.http.get(`/v1/:appId/floware/v1/datasources`);
  }

  async getDatasourceResources(
    datasourceId: string
  ): Promise<DatasourceResourcesResponse> {
    const response: IApiResponse<DatasourceResourcesData> = await this.http.get(
      `/v1/:appId/floware/v1/datasources/${datasourceId}/resources`
    );
    return response;
  }

  async createYaml(
    dataSourceId: string,
    yamlQuery: string
  ): Promise<YamlResponse> {
    const response = await this.http.put(
      `/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries`,
      {
        dynamic_query: yamlQuery,
      }
    );
    return response;
  }

  async getAllYamls(dataSourceId: string): Promise<AllYamlsResponse> {
    const response = await this.http.get(
      `/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries`
    );
    return response;
  }

  async readYaml(
    dataSourceId: string,
    yamlId: string
  ): Promise<ReadYamlResponse> {
    const response = await this.http.get(
      `/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries/${yamlId}`
    );
    return response;
  }

  async deleteYaml(
    dataSourceId: string,
    yamlId: string
  ): Promise<DeleteYamlResponse> {
    const response = await this.http.delete(
      `/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries/${yamlId}`
    );
    return response;
  }

  async executeYaml(
    dataSourceId: string,
    yamlId: string,
    params: Record<string, string>
  ): Promise<ExecuteYamlResponse> {
    const response = await this.http.post(
      `/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries/${yamlId}/execute`,
      {
        params: params,
      }
    );
    return response;
  }
}
