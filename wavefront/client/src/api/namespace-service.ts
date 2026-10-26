import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';
import { NamespaceListData, NamespaceListResponse } from '@app/types/namespace';

export class NamespaceService {
  constructor(private http: AxiosInstance) {}

  async listNamespaces(): Promise<NamespaceListResponse> {
    const response: IApiResponse<NamespaceListData> = await this.http.get(`/v1/:appId/floware/v1/namespaces`);
    return response;
  }
}
