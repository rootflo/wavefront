import floConsoleService from '@app/api';
import { NewKnowledgeBasePayload, UpdateKnowledgeBasePayload } from '@app/api/knowledge-base-service';
import {
  getKnowledgeBaseDocumentsKey,
  getKnowledgeBaseIndexStatusKey,
  getKnowledgeBaseKey,
  getKnowledgeBasesKey,
} from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
