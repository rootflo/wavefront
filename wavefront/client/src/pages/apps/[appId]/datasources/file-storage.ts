import { extractErrorMessage } from '@app/lib/errors';
import { DatasourceBrowseFileEntry, DatasourceFileEntry, DatasourceFolderEntry } from '@app/types/datasource';
import { File, FileCode, FileImage, FileSpreadsheet, FileText, FileVideo } from 'lucide-react';
import { PickedFile } from './dropped-files';

// Types, limits and pure helpers for the file storage panel

export type PreviewKind = 'image' | 'video' | 'text' | 'unsupported';

export type FilePreviewState = {
  entry: DatasourceFileEntry;
  kind: PreviewKind;
  objectUrl?: string;
  text?: string;
  contentType: string;
  sizeBytes: number;
};

/** One folder's contents as loaded so far from `files/browse`. */
export interface FolderState {
  folders: DatasourceFolderEntry[];
  files: DatasourceBrowseFileEntry[];
  /** Token for the next page; null once everything is loaded. */
  nextPageToken: string | null;
  loading: boolean;
  loaded: boolean;
  error?: string;
}

/** A file picked for upload and how far it has got. */
export interface QueuedUpload extends PickedFile {
  status: 'pending' | 'uploading' | 'done' | 'failed';
  error?: string;
}

export const TEXT_PREVIEW_MAX_BYTES = 512 * 1024;
// Rows the upload list renders; a dropped folder can hold thousands of files.
export const QUEUE_ROWS_SHOWN = 300;
export const PAGE_SIZE = 200;

/** Blob responses hide the JSON error body; read it back out for the message. */
export const getDownloadErrorMessage = async (error: unknown): Promise<string | undefined> => {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const body = JSON.parse(await data.text()) as { meta?: { error?: string } };
      return body.meta?.error;
    } catch {
      return undefined;
    }
  }
  return extractErrorMessage(error);
};

export const mimeTypeOf = (contentType: string | undefined, blobType: string) =>
  (contentType || blobType || 'application/octet-stream').split(';')[0].trim().toLowerCase();

export const previewKindFor = (mime: string): PreviewKind => {
  if (mime.startsWith('image/') && mime !== 'image/svg+xml') return 'image';
  if (mime.startsWith('video/')) return 'video';
  if (
    mime.startsWith('text/') ||
    mime === 'application/json' ||
    mime === 'application/xml' ||
    mime === 'application/javascript' ||
    mime.endsWith('+json') ||
    mime.endsWith('+xml')
  ) {
    return 'text';
  }
  return 'unsupported';
};

/** Normalize to '' or 'a/b/' (no leading slash). */
export const normalizeDirPrefix = (prefix: string): string => {
  const trimmed = prefix.replace(/^\/+/, '').replace(/\/+$/, '');
  return trimmed ? `${trimmed}/` : '';
};

export const breadcrumbSegments = (dirPrefix: string): { label: string; prefix: string }[] => {
  const trimmed = dirPrefix.replace(/^\/+|\/+$/g, '');
  if (!trimmed) return [];
  const parts = trimmed.split('/');
  return parts.map((label, index) => ({
    label,
    prefix: `${parts.slice(0, index + 1).join('/')}/`,
  }));
};

/** Every ancestor folder of a prefix, root first: 'a/b/' -> ['', 'a/', 'a/b/']. */
export const ancestorPrefixes = (dirPrefix: string): string[] => [
  '',
  ...breadcrumbSegments(dirPrefix).map((segment) => segment.prefix),
];

/** The folder a file path lives in: 'a/b/c.txt' -> 'a/b/'. */
export const parentPrefix = (path: string) => {
  const slash = path.replace(/^\/+/, '').lastIndexOf('/');
  return slash === -1 ? '' : path.replace(/^\/+/, '').slice(0, slash + 1);
};

/** An icon that hints at what a file is, from its extension. */
export const fileIconFor = (name: string) => {
  const extension = name.split('.').pop()?.toLowerCase() ?? '';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(extension)) return FileImage;
  if (['mp4', 'mov', 'webm', 'mkv', 'avi'].includes(extension)) return FileVideo;
  if (['csv', 'xls', 'xlsx', 'parquet', 'tsv'].includes(extension)) return FileSpreadsheet;
  if (['json', 'yaml', 'yml', 'xml', 'js', 'ts', 'py', 'sql', 'html'].includes(extension)) return FileCode;
  if (['txt', 'md', 'log', 'pdf', 'doc', 'docx'].includes(extension)) return FileText;
  return File;
};

export const fileTypeLabel = (name: string) => {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : 'File';
};

export const formatBytes = (bytes: number | null) => {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
};

/** One folder in the left-hand tree; its sub-folders load the first time it is expanded. */

/** How a folder prefix is shown to the user: `reports/2024/` → `reports/2024`, the root → `/`. */
export const locationLabelFor = (prefix: string) => (prefix ? prefix.replace(/\/$/, '') : '/');
