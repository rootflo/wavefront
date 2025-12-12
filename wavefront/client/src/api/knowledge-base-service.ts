import { IApiResponse } from "@app/lib/axios";
import { AxiosInstance } from "axios";

// Interface for creating a new knowledge base
export interface NewKnowledgeBasePayload {
  name: string;
  description: string;
  type: string;
  vector_size: number;
}

export interface KbData {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}
// Interface for knowledge base data
export interface KnowledgeBaseData {
  data: KbData;
}

export type KnowledgeBaseDetail = IApiResponse<KbData>;

// Interface for a single knowledge base response
export type KnowledgeBaseDetailResponse = IApiResponse<KnowledgeBaseData>;

// Interface for listing knowledge bases
export interface KnowledgeBaseListData {
  resources: KbData[];
}

export type KnowledgeBaseListResponse = IApiResponse<KnowledgeBaseListData>;

// Interface for document data
export interface DocumentData {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  updated_at: string;
}

// Interface for listing documents in a knowledge base
export interface KnowledgeBaseDocumentsListData {
  resources: DocumentData[];
}

export type KnowledgeBaseDocumentsListResponse =
  IApiResponse<KnowledgeBaseDocumentsListData>;

// Interface for RAG inference response
export interface RagInferenceResultData {
  response: string;
  sources: any[]; // Assuming sources can be any array for now
}

export type RagInferenceResponse = IApiResponse<RagInferenceResultData>;

export interface NewInferencePayload {
  prompt: string;
}

export interface InferenceData {
  inference_id: string;
  knowledge_base_id: string;
  inference_content: string;
  created_at: string;
  updated_at: string;
}
export interface AllConfigsData {
  id: string;
  llm_model: string;
  display_name: string;
  type: string;
  base_url: string;
  parameters: any;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}
export type InferenceListResponse = IApiResponse<{
  resources: InferenceData[];
}>;
export type InferenceDetailResponse = IApiResponse<InferenceData>;
export type AllConfigsResponse = IApiResponse<AllConfigsData[]>;
// Knowledge Base Service Class
export class KnowledgeBaseService {
  constructor(private http: AxiosInstance) {}

  async createKnowledgeBase(
    payload: NewKnowledgeBasePayload
  ): Promise<KnowledgeBaseDetailResponse> {
    const response: KnowledgeBaseDetailResponse = await this.http.post(
      `/v1/:appId/floware/v1/knowledge-bases`,
      payload
    );
    return response;
  }

  async listKnowledgeBases(
    offset: number = 0,
    limit: number = 10
  ): Promise<KnowledgeBaseListResponse> {
    const response: KnowledgeBaseListResponse = await this.http.get(
      `/v1/:appId/floware/v1/knowledge-bases`,
      {
        params: { offset, limit },
      }
    );
    return response;
  }

  async getKnowledgeBase(kbId: string): Promise<KnowledgeBaseDetail> {
    const response: KnowledgeBaseDetail = await this.http.get(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}`
    );
    return response;
  }

  async uploadDocument(kbId: string, file: File): Promise<IApiResponse<any>> {
    const formData = new FormData();
    formData.append("file", file);

    const response: IApiResponse<any> = await this.http.post(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}/documents`,
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
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

  async ragQuery(
    kbId: string,
    inferenceId: string,
    query: string,
    threshold?: number,
    topK?: number,
    vectorWeight?: number,
    keywordWeight?: number,
    imageData?: string
  ): Promise<RagInferenceResponse> {
    const params: Record<string, string | number> = { query };

    if (threshold) params.threshold = threshold;
    if (topK) params.top_k = topK;
    if (vectorWeight) params.vector_weight = vectorWeight;
    if (keywordWeight) params.keyword_weight = keywordWeight;

    const data: { image_data?: string } = {};
    if (imageData) {
      data.image_data = imageData;
    }

    const response: RagInferenceResponse = await this.http.post(
      `/v1/:appId/floware/v1/knowledge-base/${kbId}/augment/${inferenceId}`,
      data,
      { params }
    );
    return response;
  }

  async createSystemPrompt(
    kbId: string,
    payload: NewInferencePayload,
    configId: string
  ): Promise<InferenceDetailResponse> {
    const response: InferenceDetailResponse = await this.http.post(
      `/v1/:appId/floware/v1/knowledge-base/${kbId}/llm_config/${configId}/inference`,
      payload
    );
    return response;
  }

  async updateSystemPrompt(
    kbId: string,
    inferenceId: string,
    payload: NewInferencePayload
  ): Promise<InferenceDetailResponse> {
    const response: InferenceDetailResponse = await this.http.put(
      `/v1/:appId/floware/v1/knowledge-base/${kbId}/inference/${inferenceId}`,
      payload
    );
    return response;
  }

  async deleteSystemPrompt(
    kbId: string,
    inferenceId: string
  ): Promise<IApiResponse<any>> {
    const response: IApiResponse<any> = await this.http.delete(
      `/v1/:appId/floware/v1/knowledge-base/${kbId}/inference/${inferenceId}`
    );
    return response;
  }

  async listInferencesForKnowledgeBase(
    kbId: string
  ): Promise<InferenceListResponse> {
    const response: InferenceListResponse = await this.http.get(
      `/v1/:appId/floware/v1/knowledge-base/${kbId}/inference`
    );
    return response;
  }

  async deleteKnowledgeBase(kbId: string): Promise<IApiResponse<any>> {
    const response: IApiResponse<any> = await this.http.delete(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}`
    );
    return response;
  }

  async deleteDocument(
    kbId: string,
    documentId: string
  ): Promise<IApiResponse<any>> {
    const response: IApiResponse<any> = await this.http.delete(
      `/v1/:appId/floware/v1/knowledge-bases/${kbId}/documents/${documentId}`
    );
    return response;
  }

  async getAllConfigs(): Promise<AllConfigsResponse> {
    const response: AllConfigsResponse = await this.http.get(
      `/v1/:appId/floware/v1/llm-inference-configs`
    );
    return response;
  }
}
