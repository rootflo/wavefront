import {
  documentMimeTypeFor,
  documentTypeFor,
  validateDocumentUpload,
  validateImageUpload,
} from '@app/constants/upload';
import { useNotifyStore } from '@app/store';
import React, { useCallback, useState } from 'react';

export interface ChatImage {
  file: File;
  /** Full data URL, for previews. */
  base64: string;
  /** Just the base64 payload, for the API. */
  base64Content: string;
  mimeType: string;
}

export interface ChatDocument extends ChatImage {
  documentType: string;
}

const readAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target?.result as string);
    reader.onerror = () => reject(new Error(`Error reading ${file.name}`));
    reader.readAsDataURL(file);
  });

const toImage = async (file: File): Promise<ChatImage> => {
  const base64 = await readAsDataUrl(file);
  return { file, base64, base64Content: base64.split(',')[1] || base64, mimeType: file.type };
};

const toDocument = async (file: File): Promise<ChatDocument> => {
  const base64 = await readAsDataUrl(file);
  return {
    file,
    base64,
    base64Content: base64.split(',')[1] || base64,
    mimeType: documentMimeTypeFor(file),
    documentType: documentTypeFor(file),
  };
};

/**
 * Images and documents attached to a chat message before it's sent: picked from file inputs, checked against
 * the upload limits, and read into base64 for the inference request.
 */
export const useChatAttachments = ({ onAdded }: { onAdded?: () => void } = {}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [images, setImages] = useState<ChatImage[]>([]);
  const [documents, setDocuments] = useState<ChatDocument[]>([]);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadingDocument, setUploadingDocument] = useState(false);

  const add = useCallback(
    async <T>(
      event: React.ChangeEvent<HTMLInputElement>,
      {
        validate,
        read,
        append,
        setBusy,
        noun,
      }: {
        validate: (file: File) => string | null;
        read: (file: File) => Promise<T>;
        append: (items: T[]) => void;
        setBusy: (busy: boolean) => void;
        noun: string;
      }
    ) => {
      const input = event.target;
      const files = Array.from(input.files ?? []);
      if (files.length === 0) return;
      // All or nothing: one bad file rejects the whole pick
      const problem = files.map(validate).find(Boolean);
      if (problem) {
        notifyError(problem);
        return;
      }
      setBusy(true);
      try {
        append(await Promise.all(files.map(read)));
        notifySuccess(`${files.length} ${noun}(s) uploaded successfully`);
        onAdded?.();
      } catch (error) {
        notifyError((error as Error).message || `Error reading ${noun} files`);
      } finally {
        setBusy(false);
        // Lets the same file be picked again
        input.value = '';
      }
    },
    [notifyError, notifySuccess, onAdded]
  );

  const addImages = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) =>
      void add(event, {
        validate: validateImageUpload,
        read: toImage,
        append: (items) => setImages((prev) => [...prev, ...items]),
        setBusy: setUploadingImage,
        noun: 'image',
      }),
    [add]
  );

  const addDocuments = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) =>
      void add(event, {
        validate: validateDocumentUpload,
        read: toDocument,
        append: (items) => setDocuments((prev) => [...prev, ...items]),
        setBusy: setUploadingDocument,
        noun: 'document',
      }),
    [add]
  );

  const removeImage = useCallback((index: number) => setImages((prev) => prev.filter((_, i) => i !== index)), []);
  const removeDocument = useCallback((index: number) => setDocuments((prev) => prev.filter((_, i) => i !== index)), []);
  const clear = useCallback(() => {
    setImages([]);
    setDocuments([]);
  }, []);

  return {
    images,
    documents,
    uploadingImage,
    uploadingDocument,
    addImages,
    addDocuments,
    removeImage,
    removeDocument,
    clear,
  };
};
