import { IApiResponse } from '@app/lib/axios';
import { AxiosInstance } from 'axios';

// A knowledge base's type decides its embedding models and the files it
// accepts; the server sets the vector sizes from it and it can't be changed.
export type KnowledgeBaseType = 'text' | 'image';

export const KNOWLEDGE_BASE_TYPES: { value: KnowledgeBaseType; label: string; accepts: string }[] = [
  { value: 'text', label: 'Text', accepts: 'Text (.txt) and PDF files' },
  { value: 'image', label: 'Image', accepts: 'JPEG, PNG, GIF, WebP, BMP and TIFF images' },
];

// Interface for creating a new knowledge base
export interface NewKnowledgeBasePayload {
  name: string;
  description: string;
  type: KnowledgeBaseType;
}

// Interface for partially updating a knowledge base (type is fixed at creation)
export interface UpdateKnowledgeBasePayload {
  name?: string;
  description?: string;
}

export interface KbData {
  id: string;
  name: string;
  description: string;
  type: KnowledgeBaseType;
  created_at: string;
  updated_at: string;
}

export type KnowledgeBaseDetail = IApiResponse<KbData>;

// Interface for a single knowledge base response
export type KnowledgeBaseDetailResponse = IApiResponse<KbData>;

// Interface for listing knowledge bases
export interface KnowledgeBaseListData {
  resources: KbData[];
}

export type KnowledgeBaseListResponse = IApiResponse<KnowledgeBaseListData>;

// Where a document is in RAG indexing; null for documents uploaded before
// indexing status was tracked.
export type IndexStatus = 'QUEUED' | 'IN_PROGRESS' | 'COMPLETE' | 'FAILED';

// Interface for document data
export interface DocumentData {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  updated_at: string;
  index_status?: IndexStatus | null;
  index_error?: string | null;
}

export interface FailedDocument {
  id: string;
  file_name: string;
  index_error: string | null;
  index_status_updated_at: string | null;
}

// Document counts per indexing status (NOT_TRACKED: uploaded before tracking)
export interface KnowledgeBaseIndexStatusData {
  knowledge_base_id: string;
  total: number;
  counts: Record<IndexStatus | 'NOT_TRACKED', number>;
  failed_documents: FailedDocument[];
}

export type KnowledgeBaseIndexStatusResponse = IApiResponse<KnowledgeBaseIndexStatusData>;

// Interface for listing documents in a knowledge base
export interface KnowledgeBaseDocumentsListData {
  resources: DocumentData[];
}

export type KnowledgeBaseDocumentsListResponse = IApiResponse<KnowledgeBaseDocumentsListData>;

export interface AllConfigsData {
  id: string;
  llm_model: string;
  display_name: string;
  type: string;
  base_url: string;
  parameters: Record<string, unknown>;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}
export type AllConfigsResponse = IApiResponse<AllConfigsData[]>;
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
