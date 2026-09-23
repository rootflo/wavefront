import { IApiResponse } from '@app/lib/axios';
import {
  AllDynamicQueriesResponse,
  Datasource,
  DatasourceData,
  DatasourceResourcesData,
  DatasourceResourcesResponse,
  DatasourceResponse,
  DeleteDynamicQueryResponse,
  ExecuteDynamicQueryResponse,
  ReadDynamicQueryResponse,
  TestDatasourceData,
  TestDatasourceResponse,
  DynamicQueryResponse,
} from '@app/types/datasource';
import { AxiosInstance } from 'axios';

export class DatasourcesService {
  constructor(private http: AxiosInstance) {}

  async createDatasource(
    name: string,
    type: string,
    config: Record<string, unknown>,
    description?: string
  ): Promise<DatasourceResponse> {
    const response: IApiResponse<DatasourceData> = await this.http.post(`/v1/:appId/floware/v1/datasources`, {
      name,
      type,
      config: JSON.stringify(config),
      description,
    });
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
    config: Record<string, unknown>,
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

  async getAllDatasources(): Promise<IApiResponse<{ datasources: Datasource[] }>> {
    return this.http.get(`/v1/:appId/floware/v1/datasources`);
  }

  async getDatasourceResources(datasourceId: string): Promise<DatasourceResourcesResponse> {
    const response: IApiResponse<DatasourceResourcesData> = await this.http.get(
      `/v1/:appId/floware/v1/datasources/${datasourceId}/resources`
    );
    return response;
  }

  async createDynamicQuery(dataSourceId: string, dynamicQuery: string): Promise<DynamicQueryResponse> {
    const response = await this.http.put(`/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries`, {
      dynamic_query: dynamicQuery,
    });
    return response;
  }

  async getAllDynamicQueries(dataSourceId: string): Promise<AllDynamicQueriesResponse> {
    const response = await this.http.get(`/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries`);
    return response;
  }

  async readDynamicQuery(dataSourceId: string, queryId: string): Promise<ReadDynamicQueryResponse> {
    const response = await this.http.get(`/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries/${queryId}`);
    return response;
  }

  async deleteDynamicQuery(dataSourceId: string, queryId: string): Promise<DeleteDynamicQueryResponse> {
    const response = await this.http.delete(`/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries/${queryId}`);
    return response;
  }

  async executeDynamicQuery(
    dataSourceId: string,
    queryId: string,
    params: Record<string, string>
  ): Promise<ExecuteDynamicQueryResponse> {
    const response = await this.http.post(`/v1/:appId/floware/v1/${dataSourceId}/dynamic-queries/${queryId}/execute`, {
      params: params,
    });
    return response;
  }
}
