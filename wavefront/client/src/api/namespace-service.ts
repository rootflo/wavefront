import { IApiResponse } from "@app/lib/axios";
import { AxiosInstance } from "axios";

export interface NamespaceItem {
  name: string;
  created_at: string;
  updated_at: string;
}

export interface NamespaceListData {
  message: string;
  data: {
    namespaces: NamespaceItem[];
    count: number;
  };
}

export type NamespaceListResponse = IApiResponse<NamespaceListData>;

export class NamespaceService {
  constructor(private http: AxiosInstance) {}

  async listNamespaces(): Promise<NamespaceListResponse> {
    const response: IApiResponse<NamespaceListData> = await this.http.get(
      `/v1/:appId/floware/v1/namespaces`
    );
    return response;
  }
}
