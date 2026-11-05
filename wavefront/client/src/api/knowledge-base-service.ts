import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';
import {
  NewKnowledgeBasePayload,
  UpdateKnowledgeBasePayload,
  KnowledgeBaseDetail,
  KnowledgeBaseDetailResponse,
  KnowledgeBaseListResponse,
  KnowledgeBaseIndexStatusResponse,
  KnowledgeBaseDocumentsListResponse,
  AllConfigsResponse,
} from '@app/types/knowledge-base';

// Knowledge Base Service Class
export class KnowledgeBaseService {
  constructor(private http: AxiosInstance) {}

  async createKnowledgeBase(payload: NewKnowledgeBasePayload): Promise<KnowledgeBaseDetailResponse> {
    const response: KnowledgeBaseDetailResponse = await this.http.post(
      `/v1/:appId/floware/v1/knowledge-bases`,
      payload
    );
    return response;
  }

  async updateKnowledgeBase(kbId: string, payload: UpdateKnowledgeBasePayload): Promise<KnowledgeBaseDetailResponse> {
    const response: KnowledgeBaseDetailResponse = await this.http.patch(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}`,
      payload
    );
    return response;
  }

  async listKnowledgeBases(offset: number = 0, limit: number = 10): Promise<KnowledgeBaseListResponse> {
    const response: KnowledgeBaseListResponse = await this.http.get(`/v1/:appId/floware/v1/knowledge-bases`, {
      params: { offset, limit },
    });
    return response;
  }

  async getKnowledgeBase(kbId: string): Promise<KnowledgeBaseDetail> {
    const response: KnowledgeBaseDetail = await this.http.get(`/v1/:appId/floware/v1/knowledge-bases/${kbId}`);
    return response;
  }

  async uploadDocument(kbId: string, file: File): Promise<IApiResponse<unknown>> {
    const formData = new FormData();
    formData.append('file', file);

    const response: IApiResponse<unknown> = await this.http.post(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}/documents`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response;
  }

  async listKnowledgeBaseDocuments(
    kbId: string,
    offset: number = 0,
    limit: number = 10
  ): Promise<KnowledgeBaseDocumentsListResponse> {
    const response: KnowledgeBaseDocumentsListResponse = await this.http.get(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}/documents`,
      {
        params: { offset, limit },
      }
    );
    return response;
  }

  async getKnowledgeBaseIndexStatus(kbId: string, failedLimit: number = 20): Promise<KnowledgeBaseIndexStatusResponse> {
    const response: KnowledgeBaseIndexStatusResponse = await this.http.get(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}/index-status`,
      { params: { failed_limit: failedLimit } }
    );
    return response;
  }

  async deleteKnowledgeBase(kbId: string): Promise<IApiResponse<unknown>> {
    const response: IApiResponse<unknown> = await this.http.delete(`/v1/:appId/floware/v1/knowledge-bases/${kbId}`);
    return response;
  }

  async deleteDocument(kbId: string, documentId: string): Promise<IApiResponse<unknown>> {
    const response: IApiResponse<unknown> = await this.http.delete(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}/documents/${documentId}`
    );
    return response;
  }

  async getAllConfigs(): Promise<AllConfigsResponse> {
    const response: AllConfigsResponse = await this.http.get(`/v1/:appId/floware/v1/llm-inference-configs`);
    return response;
  }
}
