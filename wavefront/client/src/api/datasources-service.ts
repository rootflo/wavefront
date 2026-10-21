import { IApiResponse } from '@app/lib/axios';
import {
  AllDynamicQueriesResponse,
  Datasource,
  DatasourceData,
  DatasourceResourceRecordsData,
  DatasourceResourceRecordsResponse,
  DatasourceResourcesData,
  DatasourceResourcesResponse,
  DatasourceResponse,
  DeleteDatasourceResourceRowsData,
  DeleteDatasourceResourceRowsResponse,
  DeleteDynamicQueryResponse,
  ExecuteDynamicQueryResponse,
  GetDatasourceResourceParams,
  ReadDynamicQueryResponse,
  TestDatasourceData,
  TestDatasourceResponse,
  DynamicQueryResponse,
  DeleteDatasourceFileResponse,
  ListDatasourceFilesResponse,
  UploadDatasourceFileResponse,
} from '@app/types/datasource';
import { AxiosInstance, AxiosResponse } from 'axios';

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

  async listFiles(
    datasourceId: string,
    params: { prefix?: string; page_size?: number; page_number?: number } = {}
  ): Promise<ListDatasourceFilesResponse> {
    return this.http.get(`/v1/:appId/floware/v1/datasources/${datasourceId}/files/list`, {
      params,
    });
  }

  async uploadFile(datasourceId: string, file: File, path?: string): Promise<UploadDatasourceFileResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (path) {
      formData.append('path', path);
    }
    return this.http.post(`/v1/:appId/floware/v1/datasources/${datasourceId}/files`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  }

  /** `path` is the datasource://<datasource_id>/<key> path an upload returned, or a key relative to the datasource's base path. */
  async downloadFile(datasourceId: string, path: string): Promise<AxiosResponse<Blob>> {
    return this.http.get(`/v1/:appId/floware/v1/datasources/${datasourceId}/files`, {
      params: { path },
      responseType: 'blob',
    });
  }

  async deleteFile(datasourceId: string, path: string): Promise<DeleteDatasourceFileResponse> {
    return this.http.delete(`/v1/:appId/floware/v1/datasources/${datasourceId}/files`, {
      params: { path },
    });
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

  async getDatasourceResourceData(
    datasourceId: string,
    resourceId: string,
    params: GetDatasourceResourceParams = {}
  ): Promise<DatasourceResourceRecordsResponse> {
    const response: IApiResponse<DatasourceResourceRecordsData> = await this.http.get(
      `/v1/:appId/floware/v1/datasources/${datasourceId}/resources/${encodeURIComponent(resourceId)}`,
      {
        params: {
          limit: params.limit ?? 10,
          offset: params.offset ?? 0,
          ...(params.$select ? { $select: params.$select } : {}),
          ...(params.$filter ? { $filter: params.$filter } : {}),
          ...(params.$orderby ? { $orderby: params.$orderby } : {}),
        },
      }
    );
    return response;
  }

  async deleteDatasourceResourceRows(
    datasourceId: string,
    resourceId: string,
    filter: string
  ): Promise<DeleteDatasourceResourceRowsResponse> {
    const response: IApiResponse<DeleteDatasourceResourceRowsData> = await this.http.delete(
      `/v1/:appId/floware/v1/datasources/${datasourceId}/resources/${encodeURIComponent(resourceId)}`,
      {
        data: { filter },
      }
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
