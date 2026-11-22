import { IApiResponse } from '@app/lib/axios';

// A knowledge base's type decides its embedding models and the files it
// accepts; the server sets the vector sizes from it and it can't be changed.
export type KnowledgeBaseType = 'text' | 'image';

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
