import floConsoleService from '@app/api';
import {
  DocumentData,
  KbData,
  KnowledgeBaseIndexStatusData,
  NewKnowledgeBasePayload,
  UpdateKnowledgeBasePayload,
} from '@app/types/knowledge-base';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult, useQuery } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import {
  getKnowledgeBasesKey,
  getKnowledgeBaseKey,
  getKnowledgeBaseDocumentsKey,
  getKnowledgeBaseIndexStatusKey,
} from '../query-keys';

// Reads

const getKnowledgeBasesQueryFn = async (): Promise<KbData[]> => {
  const response = await floConsoleService.knowledgeBaseService.listKnowledgeBases();
  if (response.data?.meta?.status === 'success' && response.data.data?.resources) {
    return response.data.data.resources;
  }
  return [];
};

const getKnowledgeBaseQueryFn = async (kbId: string): Promise<KbData | null> => {
  const response = await floConsoleService.knowledgeBaseService.getKnowledgeBase(kbId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getKnowledgeBaseDocumentsQueryFn = async (kbId: string): Promise<DocumentData[]> => {
  const response = await floConsoleService.knowledgeBaseService.listKnowledgeBaseDocuments(kbId);
  if (response.data?.data?.resources) {
    return response.data.data.resources;
  }
  return [];
};

const getKnowledgeBaseIndexStatusQueryFn = async (kbId: string): Promise<KnowledgeBaseIndexStatusData | null> => {
  const response = await floConsoleService.knowledgeBaseService.getKnowledgeBaseIndexStatus(kbId);
  return response.data?.data ?? null;
};

export const useGetKnowledgeBases = (appId: string | undefined): UseQueryResult<KbData[], Error> => {
  return useQueryInit(getKnowledgeBasesKey(appId || ''), getKnowledgeBasesQueryFn, !!appId);
};

export const useGetKnowledgeBase = (
  appId: string | undefined,
  kbId: string | undefined
): UseQueryResult<KbData | null, Error> => {
  return useQueryInit(
    getKnowledgeBaseKey(appId || '', kbId || ''),
    () => getKnowledgeBaseQueryFn(kbId!),
    !!appId && !!kbId
  );
};

export const useGetKnowledgeBaseDocuments = (
  appId: string | undefined,
  kbId: string | undefined
): UseQueryResult<DocumentData[], Error> => {
  return useQueryInit(
    getKnowledgeBaseDocumentsKey(appId || '', kbId || ''),
    () => getKnowledgeBaseDocumentsQueryFn(kbId!),
    !!appId && !!kbId
  );
};

// While any document is queued or being indexed, refresh every few seconds so
// the counts move on their own; stop once everything has settled.
const INDEX_STATUS_POLL_MS = 5000;

export const useGetKnowledgeBaseIndexStatus = (
  appId: string | undefined,
  kbId: string | undefined
): UseQueryResult<KnowledgeBaseIndexStatusData | null, Error> => {
  return useQuery({
    queryKey: getKnowledgeBaseIndexStatusKey(appId || '', kbId || ''),
    queryFn: () => getKnowledgeBaseIndexStatusQueryFn(kbId!),
    enabled: !!appId && !!kbId,
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const counts = query.state.data?.counts;
      return counts && counts.QUEUED + counts.IN_PROGRESS > 0 ? INDEX_STATUS_POLL_MS : false;
    },
  });
};

// Writes

export const useCreateKnowledgeBase = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (payload: NewKnowledgeBasePayload) =>
      floConsoleService.knowledgeBaseService.createKnowledgeBase(payload),
    successMessage: (_, { name }) => `Knowledge Base '${name}' created successfully`,
    errorMessage: 'Failed to create knowledge base',
    invalidate: () => [appId && getKnowledgeBasesKey(appId)],
  });

export const useUpdateKnowledgeBase = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ kbId, payload }: { kbId: string; payload: UpdateKnowledgeBasePayload }) =>
      floConsoleService.knowledgeBaseService.updateKnowledgeBase(kbId, payload),
    successMessage: (_, { payload }) => `Knowledge Base '${payload.name}' updated successfully`,
    errorMessage: 'Failed to update knowledge base',
    invalidate: ({ kbId }) => (appId ? [getKnowledgeBasesKey(appId), getKnowledgeBaseKey(appId, kbId)] : []),
  });

export const useDeleteKnowledgeBase = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (kbId: string) => floConsoleService.knowledgeBaseService.deleteKnowledgeBase(kbId),
    successMessage: 'Knowledge base deleted successfully',
    errorMessage: 'Failed to delete knowledge base',
    invalidate: () => [appId && getKnowledgeBasesKey(appId)],
  });

/** Documents change the index status as well as the document list. */
const documentKeys = (appId: string | undefined, kbId: string) =>
  appId ? [getKnowledgeBaseDocumentsKey(appId, kbId), getKnowledgeBaseIndexStatusKey(appId, kbId)] : [];

export const useUploadKnowledgeBaseDocument = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ kbId, file }: { kbId: string; file: File }) =>
      floConsoleService.knowledgeBaseService.uploadDocument(kbId, file),
    successMessage: (_, { file }) => `${file.name} uploaded successfully.`,
    errorMessage: 'Failed to upload the document.',
    invalidate: ({ kbId }) => documentKeys(appId, kbId),
  });

export const useDeleteKnowledgeBaseDocument = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ kbId, documentId }: { kbId: string; documentId: string }) =>
      floConsoleService.knowledgeBaseService.deleteDocument(kbId, documentId),
    successMessage: 'Document deleted successfully.',
    errorMessage: 'Failed to delete document.',
    invalidate: ({ kbId }) => documentKeys(appId, kbId),
  });
