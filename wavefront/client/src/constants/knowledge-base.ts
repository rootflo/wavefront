import { KnowledgeBaseType } from '@app/types/knowledge-base';

export const KNOWLEDGE_BASE_TYPES: { value: KnowledgeBaseType; label: string; accepts: string }[] = [
  { value: 'text', label: 'Text', accepts: 'Text (.txt) and PDF files' },
  { value: 'image', label: 'Image', accepts: 'JPEG, PNG, GIF, WebP, BMP and TIFF images' },
];
