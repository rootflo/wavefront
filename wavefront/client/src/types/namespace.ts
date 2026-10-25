import { IApiResponse } from '@app/lib/axios';

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
